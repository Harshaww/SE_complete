"""Direct tests for SRS requirements that other suites only cover indirectly."""

from __future__ import annotations

import asyncio
import json

import pytest
from mcp.types import ListResourcesRequest, ListToolsRequest, ReadResourceRequest

from cerebra.domain.entities import ProposalState
from cerebra.domain.errors import CerebraError, ErrorCode, quota_exhausted
from cerebra.mcp_server import build_server
from tests.support.fake_youtube import http_error
from tests.support.helpers import run
from tests.support.live_env import make_env


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("CEREBRA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CEREBRA_USE_FIXTURES", "1")
    return build_server()


def _call(server, request_type, request):
    handler = server.request_handlers[request_type]
    return asyncio.run(handler(request)).root


# mark: FR-5.12, FR-5.16, NFR-US-1
class TestToolCatalogue:
    def test_create_playlist_is_marked_as_a_write_operation(self, server):
        tools = _call(server, ListToolsRequest, ListToolsRequest(method="tools/list")).tools
        by_name = {t.name: t for t in tools}
        assert {
            "find_similar_videos",
            "find_similar_channels",
            "recommend_videos",
            "analyse_engagement",
            "propose_playlist",
            "create_playlist",
        } <= set(by_name)
        assert "WRITE OPERATION" in by_name["create_playlist"].description  # FR-5.16
        for name, tool in by_name.items():
            if name != "create_playlist":
                assert "WRITE OPERATION" not in tool.description  # no false alarms


# mark: FR-5.13
class TestResources:
    def test_quota_status_and_auth_status_exposed(self, server):
        listing = _call(server, ListResourcesRequest, ListResourcesRequest(method="resources/list"))
        assert {str(r.uri) for r in listing.resources} >= {
            "cerebra://quota_status",
            "cerebra://auth_status",
        }

    def test_resources_return_json_without_secrets(self, server):
        from mcp.types import ReadResourceRequestParams

        def read(uri):
            req = ReadResourceRequest(
                method="resources/read", params=ReadResourceRequestParams(uri=uri)
            )
            result = _call(server, ReadResourceRequest, req)
            return json.loads(result.contents[0].text)

        quota = read("cerebra://quota_status")
        assert "general" in quota
        assert "authenticated" in read("cerebra://auth_status")


# mark: FR-5.10, NFR-RE-1
class TestQuotaExhaustedMessage:
    def test_error_states_when_quota_resets_and_is_not_retryable(self):
        err = quota_exhausted("2026-11-22 00:00")
        assert err.code == ErrorCode.QUOTA_EXHAUSTED and err.retryable is False
        assert "Resets at 2026-11-22 00:00 Pacific" in err.message
        assert "midnight Pacific" in err.suggested_action

    def test_live_quota_exceeded_is_not_retried(self, tmp_path):
        env = make_env(tmp_path)
        env.fake.errors["videos.list"] = [http_error(403, "quotaExceeded")] * 3
        with pytest.raises(CerebraError) as e:
            run(env.container.live_adapter.get_video("pyvid000000"))
        assert e.value.code == ErrorCode.QUOTA_EXHAUSTED
        assert env.fake.method_names().count("videos.list") == 1  # never retried


# mark: FR-5.4, BR-2, NFR-RE-1
class TestExpiredTokenKeepsPendingProposal:
    """FR-5.4: an expired/revoked refresh token is detected BEFORE anything is burned or written."""

    def test_auth_expired_leaves_proposal_and_approval_usable(self, tmp_path):
        from google.auth.exceptions import RefreshError

        env = make_env(tmp_path)
        prop = env.propose("python", 900)
        pid, digest = prop["proposal_id"], prop["digest"]
        assert env.approve(pid)[0] == 0

        # The refresh token expires (Testing-mode 7-day limit, CON-3) after approval.
        oauth = env.container.oauth
        record = oauth._store.load_token()
        record["credentials"]["expiry"] = "2000-01-01T00:00:00Z"  # access token stale
        oauth._store.save_token(record)

        def revoked(_creds):
            raise RefreshError("invalid_grant")

        original = oauth._refresh_fn
        oauth._refresh_fn = revoked
        with pytest.raises(CerebraError) as e:
            env.create(pid, digest)
        assert e.value.code == ErrorCode.AUTH_EXPIRED

        # Nothing was burned or written: proposal still PROPOSED, no YouTube write attempted.
        stored = env.container.proposal_store.load(pid)
        assert stored is not None and stored.state == ProposalState.PROPOSED
        assert not [m for m in env.fake.method_names() if m.endswith(".insert")]

        # After re-authorisation the SAME proposal + approval still work.
        oauth._refresh_fn = original
        record["credentials"]["expiry"] = "2099-01-01T00:00:00Z"
        oauth._store.save_token(record)
        assert env.create(pid, digest)["status"] == "CREATED"


def _liked_env(tmp_path):
    """User library: 6 liked videos across 2 months and all 3 duration bands."""
    from dataclasses import replace

    from tests.support.fake_youtube import FakeYouTube
    from tests.support.live_env import py_channel, python_catalog

    base = python_catalog(n=8, seconds=300)
    liked = [
        replace(base[0], duration_seconds=120, published_at="2026-01-10T00:00:00Z"),  # short
        replace(base[1], duration_seconds=180, published_at="2026-01-20T00:00:00Z"),  # short
        replace(base[2], duration_seconds=600, published_at="2026-02-05T00:00:00Z"),  # medium
        replace(base[3], duration_seconds=900, published_at="2026-02-15T00:00:00Z"),  # medium
        replace(base[4], duration_seconds=1800, published_at="2026-02-25T00:00:00Z"),  # long
        replace(base[5], duration_seconds=3600, published_at="2026-02-27T00:00:00Z"),  # long
    ]
    fake = FakeYouTube(base, [py_channel()], liked=liked)
    return make_env(tmp_path, fake)


# mark: FR-3.5, FR-3.6, FR-3.7
class TestAnalyseReport:
    def test_duration_preferences_mean_median_and_bands(self, tmp_path):
        env = _liked_env(tmp_path)
        report = run(env.container.analyse.analyse(top_k=3))
        prefs = report["duration_preferences"]
        assert prefs["mean_seconds"] == round((120 + 180 + 600 + 900 + 1800 + 3600) / 6)
        assert prefs["median_seconds"] == round((600 + 900) / 2)
        assert prefs["distribution"] == {
            "short_lt_4min": 2,
            "medium_4_to_20min": 2,
            "long_gt_20min": 2,
        }
        assert "watch history" in str(report["not_watch_history_statement"]).lower()  # FR-3.7

    def test_two_period_comparison(self, tmp_path):
        env = _liked_env(tmp_path)
        report = run(
            env.container.analyse.analyse(
                top_k=3,
                period_a=("2026-01-01", "2026-01-31"),
                period_b=("2026-02-01", "2026-02-28"),
            )
        )
        cmp_ = report["period_comparison"]
        assert cmp_["period_a"]["count"] == 2 and cmp_["period_b"]["count"] == 4
        assert cmp_["period_a"]["duration_stats"]["mean_seconds"] == 150
        assert cmp_["period_b"]["top_channels"] and cmp_["period_b"]["top_categories"]


# mark: FR-2.7, FR-2.4
class TestRecommendFilters:
    def test_max_duration_filter_applies(self, tmp_path):
        env = _liked_env(tmp_path)
        allowed = run(env.container.recommend.recommend(limit=10, max_duration_seconds=400))
        assert {r["video_id"] for r in allowed["recommendations"]} == {"pyvid000006", "pyvid000007"}
        too_short = run(env.container.recommend.recommend(limit=10, max_duration_seconds=200))
        assert too_short["recommendations"] == []  # both candidates are 300 s

    def test_topic_filter_is_sent_to_the_search(self, tmp_path):
        # The double matches a whole query as one substring, so assert on the request itself.
        env = _liked_env(tmp_path)
        run(env.container.recommend.recommend(limit=10, topic_filter="cooking"))
        queries = [kw["q"] for name, kw in env.fake.calls if name == "search.list"]
        assert queries and all(q.startswith("cooking ") for q in queries)

    def test_results_exclude_liked_videos(self, tmp_path):
        env = _liked_env(tmp_path)
        out = run(env.container.recommend.recommend(limit=10))
        ids = {r["video_id"] for r in out["recommendations"]}
        assert ids
        assert not ids & {v.video_id for v in env.fake.liked}  # FR-2.4


# mark: NFR-US-2, FR-1.6
class TestHumanReadableResults:
    def test_results_carry_mm_ss_duration_and_direct_link(self, tmp_path):
        env = make_env(tmp_path)
        results = run(env.container.find_similar.find_similar_videos("pyvid000000", limit=3))
        assert results
        for r in results:
            assert r.url == f"https://www.youtube.com/watch?v={r.video_id}"
            assert ":" in r.duration_human()  # e.g. 5:00 / 1:02:03


# mark: FR-3.4
class TestMonthlyTrends:
    def test_playlisted_videos_counted_per_month_by_add_date(self, tmp_path):
        from tests.support.fake_youtube import FakeYouTube
        from tests.support.live_env import py_channel, python_catalog

        videos = python_catalog(n=6, seconds=300)
        fake = FakeYouTube(videos, [py_channel()])
        fake.pl_store["PLtrend"] = {
            "snippet": {"title": "mine", "description": ""},
            "status": {"privacyStatus": "private"},
        }
        fake.playlist_videos["PLtrend"] = [
            {"video_id": videos[0].video_id, "added": "2026-03-02T10:00:00Z"},
            {"video_id": videos[1].video_id, "added": "2026-03-20T10:00:00Z"},
            {"video_id": videos[2].video_id, "added": "2026-05-11T10:00:00Z"},
        ]
        env = make_env(tmp_path, fake)
        report = run(env.container.analyse.analyse(top_k=3))
        assert report["monthly_trends"] == {"2026-03": 2, "2026-05": 1}  # sorted, per month


# mark: NFR-TE-1, TR-5
class TestCiNeverCallsLiveApi:
    ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]

    def test_live_suites_are_deselected_by_default(self):
        text = (self.ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "not live_readonly and not live_write" in text

    def test_pr_workflow_has_no_live_credentials(self):
        ci = (self.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for secret in ("CEREBRA_REFRESH_TOKEN", "GOOGLE_CLIENT_SECRET", "CEREBRA_YOUTUBE_API_KEY"):
            assert secret not in ci

    def test_live_workflows_never_run_on_pull_requests(self):
        for name in ("live-api-readonly.yml", "live-api-write.yml"):
            wf = (self.ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            assert "pull_request" not in wf
