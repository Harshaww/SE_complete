"""Human approval provenance on the LIVE path (FR-4.6, FR-4.7, NFR-SA-1, ADR-A)."""

# mark: FR-4.6, FR-4.7, NFR-SA-1, NFR-SA-2, ADR-A
from __future__ import annotations

import io

import pytest

from cerebra.cli import main as cli_main
from cerebra.cli import safe_terminal_text
from cerebra.domain.entities import ProposalState
from cerebra.domain.errors import CerebraError, ErrorCode
from cerebra.mcp_server import _dispatch
from tests.support.fake_youtube import FakeYouTube
from tests.support.helpers import run
from tests.support.live_env import make_env, python_catalog

WRITES = {"playlists.insert", "playlistItems.insert"}


def writes(env):
    return [n for n in env.fake.method_names() if n in WRITES]


def err_code(fn, *a):
    with pytest.raises(CerebraError) as e:
        fn(*a)
    return e.value.code


@pytest.fixture
def env(tmp_path):
    return make_env(tmp_path)


# mark: FR-4.6, FR-4.7, NFR-SA-1, NFR-SA-2, ADR-A, BR-1, BR-2
class TestNoWriteWithoutHumanApproval:
    def test_digest_alone_is_not_enough(self, env):
        prop = env.propose()
        code = err_code(env.create, prop["proposal_id"], prop["digest"])
        assert code == ErrorCode.APPROVAL_REJECTED
        assert writes(env) == []
        assert (
            env.container.proposal_store.load(prop["proposal_id"]).state == ProposalState.PROPOSED
        )

    def test_confirmed_true_flag_is_ignored_via_mcp_dispatch(self, env):
        prop = env.propose()
        args = {
            "proposal_id": prop["proposal_id"],
            "confirmation_digest": prop["digest"],
            "confirmed": True,
            "approved": True,
            "force": True,
        }
        with pytest.raises(CerebraError) as e:
            run(_dispatch("create_playlist", args, env.container))
        assert e.value.code == ErrorCode.APPROVAL_REJECTED and writes(env) == []

    def test_mcp_has_no_approve_tool(self, env):
        with pytest.raises(CerebraError) as e:
            run(_dispatch("approve_playlist", {"proposal_id": "x"}, env.container))
        assert e.value.code == ErrorCode.INVALID_ARGUMENT

    def test_wrong_digest_rejected_even_with_approval(self, env):
        prop = env.propose()
        assert env.approve(prop["proposal_id"])[0] == 0
        assert err_code(env.create, prop["proposal_id"], "0" * 64) == ErrorCode.APPROVAL_REJECTED
        assert writes(env) == []

    def test_approval_with_tampered_digest_rejected(self, env):
        prop = env.propose()
        env.container.approvals.record(
            prop["proposal_id"], "f" * 64, "UCaccount0000000000000000", "t"
        )
        assert (
            err_code(env.create, prop["proposal_id"], prop["digest"]) == ErrorCode.APPROVAL_REJECTED
        )
        assert writes(env) == []

    def test_approval_for_other_account_rejected(self, env):
        prop = env.propose()
        env.container.approvals.record(prop["proposal_id"], prop["digest"], "UCsomeoneelse", "t")
        assert (
            err_code(env.create, prop["proposal_id"], prop["digest"]) == ErrorCode.APPROVAL_REJECTED
        )

    def test_proposal_from_other_account_rejected(self, env, tmp_path):
        prop = env.propose()
        env.approve(prop["proposal_id"])
        other = make_env(
            tmp_path,
            FakeYouTube(python_catalog(), [], account_channel_id="UCotheraccount000000000"),
        )
        # same SQLite file (same data_dir) → same proposal store, different logged-in account
        assert (
            err_code(other.create, prop["proposal_id"], prop["digest"])
            == ErrorCode.APPROVAL_REJECTED
        )
        assert writes(other) == []


# mark: FR-4.6, FR-4.7, NFR-SA-1, NFR-SA-2, ADR-A
class TestHappyPathAndSingleUse:
    def test_approve_then_create_writes_exactly_the_approved_items(self, env):
        prop = env.propose()
        code, out, err = env.approve(prop["proposal_id"])
        assert code == 0 and "Approved" in err
        res = env.create(prop["proposal_id"], prop["digest"], "private")
        assert res["status"] == "CREATED"
        n = len(prop["items"])
        assert writes(env) == ["playlists.insert"] + ["playlistItems.insert"] * n
        assert {c[0] for c in env.fake.calls} <= {
            "search.list",
            "videos.list",
            "channels.list",
            "playlists.insert",
            "playlistItems.insert",
        }
        assert sorted(
            e["video_id"] for e in env.fake.playlist_videos[res["playlist_id"]]
        ) == sorted(i["video_id"] for i in prop["items"])

    def test_replay_rejected_and_no_second_write(self, env):
        prop = env.propose()
        env.approve(prop["proposal_id"])
        env.create(prop["proposal_id"], prop["digest"])
        before = len(writes(env))
        code = err_code(env.create, prop["proposal_id"], prop["digest"])
        assert code in (ErrorCode.PROPOSAL_ALREADY_USED, ErrorCode.PROPOSAL_INVALID_STATE)
        assert len(writes(env)) == before

    def test_approval_is_single_use(self, env):
        prop = env.propose()
        env.approve(prop["proposal_id"])
        env.create(prop["proposal_id"], prop["digest"])
        assert env.container.approvals.get(prop["proposal_id"])["used"] == "1"
        assert env.container.approvals.consume(prop["proposal_id"]) is False

    def test_expired_proposal_rejected_despite_approval(self, env):
        prop = env.propose()
        env.approve(prop["proposal_id"])
        env.clock.advance(901)
        assert (
            err_code(env.create, prop["proposal_id"], prop["digest"]) == ErrorCode.PROPOSAL_EXPIRED
        )
        assert writes(env) == []

    def test_privacy_defaults_private_and_public_is_explicit(self, env):
        prop = env.propose()
        env.approve(prop["proposal_id"])
        env.create(prop["proposal_id"], prop["digest"], "public")
        body = next(kw for n, kw in env.fake.calls if n == "playlists.insert")["body"]
        assert body["status"]["privacyStatus"] == "public"
        assert prop["proposal_id"] in body["snippet"]["description"]
        assert not body["snippet"]["title"].startswith(
            "[DATA]"
        )  # real title, not the LLM delimiter


# mark: FR-4.6, FR-4.7, NFR-SA-1, NFR-SA-2, ADR-A
class TestApproveCli:
    def test_refuses_without_tty_and_records_nothing(self, env):
        prop = env.propose()
        code, out, err = env.approve(prop["proposal_id"], tty=False)
        assert code == 2 and "interactive terminal" in err
        assert env.container.approvals.get(prop["proposal_id"]) is None

    @pytest.mark.parametrize("typed", ["", "wrong123", "   "])
    def test_wrong_confirmation_records_nothing(self, env, typed):
        prop = env.propose()
        code, _, err = env.approve(prop["proposal_id"], typed=typed)
        assert code == 1 and "Not approved" in err
        assert env.container.approvals.get(prop["proposal_id"]) is None

    def test_unknown_proposal(self, env):
        code, _, err = env.approve("11111111-1111-4111-8111-111111111111", typed="x")
        assert code == 1 and "No proposal" in err

    def test_non_proposed_state_refused(self, env):
        prop = env.propose()
        env.approve(prop["proposal_id"])
        env.create(prop["proposal_id"], prop["digest"])
        code, _, err = env.approve(prop["proposal_id"], typed="x")
        assert code == 1 and "CREATED" in err

    def test_expired_refused(self, env):
        prop = env.propose()
        env.clock.advance(1000)
        code, _, err = env.approve(prop["proposal_id"], typed="x")
        assert code == 1 and "expired" in err

    def test_invalid_id_format(self, env):
        out, err = io.StringIO(), io.StringIO()
        code = cli_main(
            ["approve", "../../etc/passwd"],
            container_factory=lambda: env.container,
            input_fn=lambda p: "",
            isatty=lambda: True,
            out=out,
            err=err,
        )
        assert code == 1 and "INVALID_ARGUMENT" in err.getvalue()

    def test_terminal_escape_sequences_in_titles_are_neutralised(self, env):
        evil = "\x1b[2J\x1b]0;pwned\x07Nice video‮"
        assert "\x1b" not in safe_terminal_text(evil) and "\x07" not in safe_terminal_text(evil)
        assert "‮" not in safe_terminal_text(evil)
        assert len(safe_terminal_text("x" * 500)) == 120
        prop = env.propose()
        p = env.container.proposal_store.load(prop["proposal_id"])
        from dataclasses import replace

        p.items[0] = replace(p.items[0], title=evil)
        env.container.proposal_store.save(p)
        _, _, err = env.approve(prop["proposal_id"])
        assert "\x1b" not in err and "\x07" not in err

    def test_other_commands(self, env):
        out, err = io.StringIO(), io.StringIO()
        for cmd in (["status"], ["pending"]):
            assert cli_main(cmd, container_factory=lambda: env.container, out=out, err=err) == 0
        assert '"mode": "live"' in out.getvalue()
        assert "ya29" not in out.getvalue() and "csecret" not in out.getvalue()
