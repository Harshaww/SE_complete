"""ADR-C write protocol, recovery, quota preflight, incremental auth, composition (Phase 3/4)."""

# mark: FR-4.13, FR-5.1, FR-5.8, ADR-B, ADR-C, ADR-D
from __future__ import annotations

import io
import json
import uuid

import pytest

from cerebra.adapters.fixtures.fixture_adapter import FixturePlaylistWriter
from cerebra.application.playlist import CreatePlaylistUseCase
from cerebra.cli import main as cli_main
from cerebra.domain.entities import PlaylistItem, PlaylistProposal, ProposalState
from cerebra.domain.errors import CerebraError, ErrorCode
from cerebra.domain.quota import QuotaLedger
from cerebra.infrastructure.auth.oauth_manager import SCOPE_READONLY, SCOPE_WRITE
from cerebra.infrastructure.clock import FakeClock
from cerebra.infrastructure.composition import build_container
from tests.support.fake_youtube import FakeYouTube, http_error
from tests.support.helpers import run
from tests.support.live_env import NOW, make_env, py_channel, python_catalog, token_record


def approved(env, **kw):
    prop = env.propose(**kw)
    assert env.approve(prop["proposal_id"])[0] == 0
    return prop


def count(env, name):
    return env.fake.method_names().count(name)


def load(env, pid):
    return env.container.proposal_store.load(pid)


def code_of(fn, *a):
    with pytest.raises(CerebraError) as e:
        fn(*a)
    return e.value.code


class InspectingWriter(FixturePlaylistWriter):
    """Records what the proposal store looked like at the moment of each write (ADR-C §2)."""

    def __init__(self, store, pid):
        super().__init__()
        self.store, self.pid, self.snapshots = store, pid, []

    async def create_playlist(self, title, description, privacy_status):
        p = self.store.load(self.pid)
        self.snapshots.append(("create", p.state, dict(p.item_states), p.playlist_id))
        return await super().create_playlist(title, description, privacy_status)

    async def add_playlist_item(self, playlist_id, video_id, position):
        p = self.store.load(self.pid)
        self.snapshots.append((video_id, p.state, dict(p.item_states), position))
        return await super().add_playlist_item(playlist_id, video_id, position)


# mark: FR-4.13, FR-5.1, FR-5.8, ADR-B, ADR-C, ADR-D
class TestStatePersistedBeforeEachWrite:
    def test_snapshots(self, proposal_store, audit_log, clock, config):
        import datetime

        pid = str(uuid.uuid4())
        items = [PlaylistItem(f"vid{i}ABCDEFG"[:11], "t", "c", 60) for i in range(3)]
        exp = datetime.datetime.fromtimestamp(
            clock.utcnow_timestamp() + 900, tz=datetime.UTC
        ).isoformat()
        proposal_store.save(
            PlaylistProposal(
                pid,
                "topic",
                180,
                None,
                None,
                items,
                clock.utcnow_iso(),
                exp,
                ProposalState.PROPOSED,
                "a" * 64,
            )
        )
        w = InspectingWriter(proposal_store, pid)
        uc = CreatePlaylistUseCase(w, QuotaLedger(), proposal_store, audit_log, clock, config)
        assert run(uc.create(pid, "a" * 64))["status"] == "CREATED"

        kind, state, states, playlist_id = w.snapshots[0]
        assert kind == "create" and state == ProposalState.PARTIAL and playlist_id is None
        assert set(states.values()) == {"PENDING"}
        for n, (vid, state, states, position) in enumerate(w.snapshots[1:]):
            assert state == ProposalState.PARTIAL and position == n
            assert states[vid] == "PENDING"
            assert all(states[i.video_id] == "INSERTED" for i in items[:n])
        final = proposal_store.load(pid)
        assert final.state == ProposalState.CREATED and set(final.item_states.values()) == {
            "INSERTED"
        }

    def test_constructor_requires_store_when_approval_required(
        self, proposal_store, audit_log, clock, config
    ):
        with pytest.raises(ValueError):
            CreatePlaylistUseCase(
                FixturePlaylistWriter(),
                QuotaLedger(),
                proposal_store,
                audit_log,
                clock,
                config,
                require_approval=True,
            )


# mark: FR-4.13, FR-5.1, FR-5.8, ADR-B, ADR-C, ADR-D
class TestFailureHandling:
    def test_definitive_create_failure_becomes_failed(self, tmp_path):
        env = make_env(tmp_path)
        prop = approved(env)
        env.fake.errors["playlists.insert"] = [http_error(400, "invalid")]
        assert (
            code_of(env.create, prop["proposal_id"], prop["digest"]) == ErrorCode.YOUTUBE_API_ERROR
        )
        assert load(env, prop["proposal_id"]).state == ProposalState.FAILED
        assert count(env, "playlistItems.insert") == 0

    def test_ambiguous_create_failure_stays_partial_and_is_audited(self, tmp_path):
        env = make_env(tmp_path)
        prop = approved(env)
        env.fake.errors["playlists.insert"] = [http_error(503)]
        assert (
            code_of(env.create, prop["proposal_id"], prop["digest"]) == ErrorCode.PARTIAL_CREATION
        )
        p = load(env, prop["proposal_id"])
        assert p.state == ProposalState.PARTIAL and p.ambiguous and p.playlist_id is None
        events = env.container.proposal_store._db.execute("SELECT event FROM audit_log")
        assert any("ambiguous_failure:playlists.insert" in r["event"] for r in events)
        assert count(env, "playlists.insert") == 1  # never blind-retried

    def test_item_failure_midway_is_partial_with_contiguous_positions(self, tmp_path):
        env = make_env(tmp_path)
        prop = approved(env)
        n = len(prop["items"])
        assert n >= 3
        env.fake.errors["playlistItems.insert"] = [None, http_error(400, "bad"), None]
        res = env.create(prop["proposal_id"], prop["digest"])
        assert res["status"] == "PARTIAL" and len(res["failed_video_ids"]) == 1
        positions = [
            kw["body"]["snippet"]["position"]
            for nme, kw in env.fake.calls
            if nme == "playlistItems.insert"
        ]
        assert positions == [0, 1, 1][: len(positions)]  # failed item leaves no gap
        assert "cerebra-cli recover" in res["message"]

    def test_quota_exhaustion_stops_the_item_loop(self, tmp_path):
        env = make_env(tmp_path)
        prop = approved(env)
        env.fake.errors["playlistItems.insert"] = [None, http_error(403, "quotaExceeded")]
        res = env.create(prop["proposal_id"], prop["digest"])
        assert res["status"] == "PARTIAL"
        assert count(env, "playlistItems.insert") == 2  # stopped, did not hammer the API
        p = load(env, prop["proposal_id"])
        assert list(p.item_states.values()).count("PENDING") == len(prop["items"]) - 2

    def test_preflight_refuses_before_any_write_and_keeps_approval(self, tmp_path):
        # budget passes propose's up-front check, then other usage leaves < 50 + 50n units
        env = make_env(tmp_path, budget=1100)
        prop = approved(env)
        env.container.quota.consume("videos.list", 850)  # e.g. other tools used the quota
        used_before = env.container.quota.status()["general"]["used"]
        assert (
            code_of(env.create, prop["proposal_id"], prop["digest"])
            == ErrorCode.QUOTA_BUDGET_EXCEEDED
        )
        assert count(env, "playlists.insert") == 0
        assert load(env, prop["proposal_id"]).state == ProposalState.PROPOSED
        assert env.container.approvals.get(prop["proposal_id"])["used"] == "0"
        assert env.container.quota.status()["general"]["used"] == used_before


# mark: FR-4.13, FR-5.1, FR-5.8, ADR-B, ADR-C, ADR-D
class TestRecovery:
    def recover(self, env, pid):
        return run(env.container.recover.recover(pid))

    def test_adopts_existing_playlist_after_ambiguous_create_no_duplicate(self, tmp_path):
        env = make_env(tmp_path)
        prop = approved(env)
        env.fake.errors["playlists.insert"] = [http_error(503)]
        env.fake.apply_then_fail = {"playlists.insert"}  # created remotely, response lost
        code_of(env.create, prop["proposal_id"], prop["digest"])
        res = self.recover(env, prop["proposal_id"])
        assert res["status"] == "CREATED" and any("adopted" in n for n in res["notes"])
        assert count(env, "playlists.insert") == 1  # NO duplicate playlist
        assert len(env.fake.pl_store) == 1
        assert len(env.fake.playlist_videos[res["playlist_id"]]) == len(prop["items"])
        assert load(env, prop["proposal_id"]).state == ProposalState.CREATED

    def test_creates_once_when_playlist_truly_absent(self, tmp_path):
        env = make_env(tmp_path)
        prop = approved(env)
        env.fake.errors["playlists.insert"] = [http_error(503)]  # NOT applied
        code_of(env.create, prop["proposal_id"], prop["digest"])
        res = self.recover(env, prop["proposal_id"])
        assert res["status"] == "CREATED" and any("created it once" in n for n in res["notes"])
        assert count(env, "playlists.insert") == 2 and len(env.fake.pl_store) == 1

    def test_inserts_only_missing_items(self, tmp_path):
        env = make_env(tmp_path)
        prop = approved(env)
        env.fake.errors["playlistItems.insert"] = [None, http_error(400, "x")]
        first = env.create(prop["proposal_id"], prop["digest"])
        inserted_before = count(env, "playlistItems.insert")
        res = self.recover(env, prop["proposal_id"])
        assert res["status"] == "CREATED"
        assert count(env, "playlistItems.insert") - inserted_before == len(
            first["failed_video_ids"]
        )
        ids = [e["video_id"] for e in env.fake.playlist_videos[first["playlist_id"]]]
        assert len(ids) == len(set(ids)) == len(prop["items"])  # no duplicate items

    def test_ambiguous_item_that_actually_landed_is_not_reinserted(self, tmp_path):
        env = make_env(tmp_path)
        prop = approved(env)
        env.fake.errors["playlistItems.insert"] = [http_error(503)]
        env.fake.apply_then_fail = {"playlistItems.insert"}
        first = env.create(prop["proposal_id"], prop["digest"])
        assert first["status"] == "PARTIAL"
        before = count(env, "playlistItems.insert")
        res = self.recover(env, prop["proposal_id"])
        assert res["status"] == "CREATED"
        assert count(env, "playlistItems.insert") == before  # read-before-retry: nothing to add
        ids = [e["video_id"] for e in env.fake.playlist_videos[first["playlist_id"]]]
        assert len(ids) == len(set(ids))

    def test_recovery_reads_remote_state_first(self, tmp_path):
        env = make_env(tmp_path)
        prop = approved(env)
        env.fake.errors["playlistItems.insert"] = [http_error(400, "x")]
        env.create(prop["proposal_id"], prop["digest"])
        mark = len(env.fake.calls)
        self.recover(env, prop["proposal_id"])
        names = [n for n, _ in env.fake.calls[mark:]]
        assert names.index("playlistItems.list") < names.index("playlistItems.insert")

    def test_still_failing_stays_partial(self, tmp_path):
        env = make_env(tmp_path)
        prop = approved(env)
        env.fake.errors["playlistItems.insert"] = [http_error(400, "x")] * 10
        env.create(prop["proposal_id"], prop["digest"])
        res = self.recover(env, prop["proposal_id"])
        assert res["status"] == "PARTIAL" and res["failed_video_ids"]
        assert load(env, prop["proposal_id"]).state == ProposalState.PARTIAL

    def test_quota_exhausted_during_recovery_stops(self, tmp_path):
        env = make_env(tmp_path)
        prop = approved(env)
        env.fake.errors["playlistItems.insert"] = [http_error(400, "x")] * 3
        env.create(prop["proposal_id"], prop["digest"])
        env.fake.errors["playlistItems.insert"] = [http_error(403, "quotaExceeded")]
        res = self.recover(env, prop["proposal_id"])
        assert res["status"] == "PARTIAL"

    def test_crash_between_confirmed_and_partial(self, tmp_path):
        env = make_env(tmp_path)
        prop = approved(env)
        env.container.proposal_store.update_state(
            prop["proposal_id"], state=ProposalState.CONFIRMED
        )
        assert [p.proposal_id for p in env.container.recover.pending()] == [prop["proposal_id"]]
        assert self.recover(env, prop["proposal_id"])["status"] == "CREATED"

    def test_claimed_inserted_but_missing_remotely_is_reinserted(self, tmp_path):
        env = make_env(tmp_path)
        prop = approved(env)
        env.create(prop["proposal_id"], prop["digest"])
        pid = prop["proposal_id"]
        p = load(env, pid)
        env.container.proposal_store.update_state(pid, state=ProposalState.PARTIAL)
        env.fake.playlist_videos[p.playlist_id].pop()  # someone removed one remotely
        res = self.recover(env, pid)
        assert res["status"] == "CREATED"
        assert len(env.fake.playlist_videos[p.playlist_id]) == len(prop["items"])

    def test_noop_unknown_and_other_account(self, tmp_path):
        env = make_env(tmp_path)
        prop = approved(env)
        env.create(prop["proposal_id"], prop["digest"])
        assert "Nothing to recover" in self.recover(env, prop["proposal_id"])["message"]
        assert code_of(lambda: self.recover(env, str(uuid.uuid4()))) == ErrorCode.PROPOSAL_NOT_FOUND
        env.fake.errors["playlistItems.insert"] = []
        other = make_env(
            tmp_path,
            FakeYouTube(python_catalog(), [], account_channel_id="UCother000000000000000000"),
        )
        pid = other.propose()["proposal_id"]  # separate proposal, different account
        other.container.proposal_store.update_state(pid, state=ProposalState.PARTIAL)
        mine = make_env(tmp_path)
        assert code_of(lambda: self.recover(mine, pid)) == ErrorCode.APPROVAL_REJECTED

    def test_recovery_quota_preflight(self, tmp_path):
        env = make_env(tmp_path, budget=1100)
        prop = approved(env)
        env.container.quota.consume("videos.list", 950)
        env.container.proposal_store.update_state(prop["proposal_id"], state=ProposalState.PARTIAL)
        assert (
            code_of(lambda: self.recover(env, prop["proposal_id"]))
            == ErrorCode.QUOTA_BUDGET_EXCEEDED
        )
        assert count(env, "playlists.insert") == 0

    def test_cli_recover_and_pending(self, tmp_path):
        env = make_env(tmp_path)
        prop = approved(env)
        env.fake.errors["playlistItems.insert"] = [http_error(400, "x")]
        env.create(prop["proposal_id"], prop["digest"])
        out, err = io.StringIO(), io.StringIO()
        cli_main(["pending"], container_factory=lambda: env.container, out=out, err=err)
        pending = json.loads(out.getvalue())
        assert pending[0]["proposal_id"] == prop["proposal_id"] and pending[0]["missing_items"]
        out = io.StringIO()
        assert (
            cli_main(
                ["recover", prop["proposal_id"]],
                container_factory=lambda: env.container,
                out=out,
                err=err,
            )
            == 0
        )
        assert json.loads(out.getvalue())["status"] == "CREATED"


class FakeFlow:
    instances = []

    def __init__(self, config, scopes):
        self.scopes = scopes
        FakeFlow.instances.append(self)

    def run_local_server(self, **kw):
        class C:
            scopes = self.scopes

            def to_json(s):
                return json.dumps(token_record(self.scopes)["credentials"])

        return C()


# mark: FR-4.13, FR-5.1, FR-5.8, ADR-B, ADR-C, ADR-D
class TestIncrementalAuth:
    def test_create_upgrades_readonly_to_write_scope(self, tmp_path):
        FakeFlow.instances.clear()
        env = make_env(tmp_path, scopes=(SCOPE_READONLY,), interactive=True, flow_factory=FakeFlow)
        prop = approved(env)
        assert env.create(prop["proposal_id"], prop["digest"])["status"] == "CREATED"
        assert set(FakeFlow.instances[0].scopes) == {SCOPE_READONLY, SCOPE_WRITE}
        assert env.oauth.has_scope(SCOPE_WRITE)

    def test_noninteractive_without_write_scope_fails_before_any_state_change(self, tmp_path):
        env = make_env(tmp_path, scopes=(SCOPE_READONLY,), interactive=False)
        prop = approved(env)
        assert (
            code_of(env.create, prop["proposal_id"], prop["digest"]) == ErrorCode.INSUFFICIENT_SCOPE
        )
        assert load(env, prop["proposal_id"]).state == ProposalState.PROPOSED
        assert env.container.approvals.get(prop["proposal_id"])["used"] == "0"
        assert count(env, "playlists.insert") == 0

    def test_readonly_token_cannot_reach_write_endpoints_directly(self, tmp_path):
        env = make_env(tmp_path, scopes=(SCOPE_READONLY,), interactive=False)
        assert (
            code_of(lambda: run(env.container.live_adapter.create_playlist("t", "d", "private")))
            == ErrorCode.INSUFFICIENT_SCOPE
        )
        assert env.fake.calls == []


# mark: FR-4.13, FR-5.1, FR-5.8, ADR-B, ADR-C, ADR-D
class TestCompositionAndQuota:
    def test_live_mode_wiring(self, tmp_path):
        env = make_env(tmp_path)
        c = env.container
        assert c.live and c.live_adapter is not None and c.oauth is env.oauth
        assert c.create_pl._require_approval is True  # live writes ALWAYS need CLI approval
        assert c.propose._video is c.live_adapter

    def test_fixture_mode_unchanged(self, tmp_path):
        from cerebra.config import Config

        cfg = Config()
        cfg.data_dir = tmp_path / "d"
        c = build_container(cfg)
        assert not c.live and c.oauth is None and c.is_authenticated is True

    def test_auth_flag_is_dynamic(self, tmp_path):
        env = make_env(tmp_path, token=False)
        assert code_of(lambda: env.propose()) == ErrorCode.AUTH_REQUIRED
        env.store.save_token(token_record())
        assert env.propose()["items"]

    def test_no_double_counting_between_use_case_and_adapter(self, tmp_path):
        env = make_env(tmp_path)
        run(env.container.find_similar.find_similar_videos("pyvid000000", 5))
        costs = {"search.list": 100}
        expected = sum(costs.get(n, 1) for n in env.fake.method_names())
        st = env.container.quota.status()
        assert st["general"]["used"] == expected and st["general"]["reserved"] == 0
        assert st["search"]["used"] == env.fake.method_names().count("search.list")

    def test_over_budget_find_similar_makes_zero_api_calls(self, tmp_path):
        env = make_env(tmp_path, budget=10)
        assert (
            code_of(lambda: run(env.container.find_similar.find_similar_videos("pyvid000000", 5)))
            == ErrorCode.QUOTA_BUDGET_EXCEEDED
        )
        assert env.fake.calls == []

    def test_quota_persists_across_restart_and_resets_next_pacific_day(self, tmp_path):
        env = make_env(tmp_path)
        run(env.container.live_adapter.get_video("pyvid000000"))
        assert env.container.quota.status()["general"]["used"] == 1
        again = make_env(tmp_path, clock=FakeClock(NOW))  # "restart": same DB file
        assert again.container.quota.status()["general"]["used"] == 1
        later = make_env(tmp_path, clock=FakeClock(NOW + 2 * 86400))
        st = later.container.quota.status()
        assert st["general"]["used"] == 0 and "day_pacific" in st
        # rollover while running
        env.clock.advance(2 * 86400)
        assert env.container.quota.can_afford(general=10_000)
        assert env.container.quota.status()["general"]["used"] == 0

    def test_recommend_flow_uses_library_endpoints_readonly(self, tmp_path):
        liked = python_catalog(3)
        fake = FakeYouTube(python_catalog(), [py_channel()], liked=liked)
        env = make_env(tmp_path, fake, scopes=(SCOPE_READONLY,))
        res = run(env.container.recommend.recommend(limit=3))
        assert "recommendations" in res
        assert not {"playlists.insert", "playlistItems.insert"} & set(fake.method_names())
