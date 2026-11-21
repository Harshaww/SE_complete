"""LIVE read-only smoke tests against the real YouTube Data API v3.

Scheduled / manual only (.github/workflows/live-api-readonly.yml). Deselected by default and
skipped without credentials, so PR CI never calls the live API (NFR-TE-1, TR-5, AGENTS rule 9).
Never writes to YouTube. Costs a few hundred quota units at most (CEREBRA_QUOTA_BUDGET).
"""

# mark: FR-1.1, FR-1.2, FR-5.7, FR-5.8, FR-5.17, TR-5, TR-6, NFR-CO-1, NFR-SE-2
from __future__ import annotations

import json
import os

import pytest

from cerebra.domain.errors import CerebraError, ErrorCode
from tests.support.helpers import run
from tests.support.live_real import (
    NONEXISTENT_VIDEO,
    STABLE_PUBLIC_VIDEO,
    build_live_container,
    live_env_missing,
)

_SKIP = live_env_missing()
pytestmark = [
    pytest.mark.live_readonly,
    pytest.mark.skipif(bool(_SKIP), reason=_SKIP or "live env available"),
]


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    """One container for the whole module so the quota ledger spans every live call."""
    return build_live_container(tmp_path_factory.mktemp("live_ro"), budget=500)


def _used(container) -> int:
    return int(container.quota.status()["general"]["used"])


# mark: FR-5.1, FR-5.2, NFR-SE-2
class TestLiveAuth:
    def test_headless_token_is_authenticated_and_never_leaked(self, live):
        status = live.oauth.status()
        assert status["authenticated"] is True
        assert live.oauth.headless
        dumped = json.dumps(status)
        assert os.environ["CEREBRA_REFRESH_TOKEN"] not in dumped


# mark: FR-1.2, FR-5.17, NFR-CO-1
class TestLiveVideoReads:
    def test_public_video_metadata(self, live):
        video = run(live.live_adapter.get_video(STABLE_PUBLIC_VIDEO))
        assert video.video_id == STABLE_PUBLIC_VIDEO
        assert video.title and video.duration_seconds > 0 and video.channel_id

    def test_unknown_video_maps_to_not_found(self, live):
        with pytest.raises(CerebraError) as err:
            run(live.live_adapter.get_video(NONEXISTENT_VIDEO))
        assert err.value.code == ErrorCode.VIDEO_NOT_FOUND_OR_PRIVATE

    def test_malformed_reference_rejected_without_api_call(self, live):
        before = _used(live)
        with pytest.raises(CerebraError) as err:
            run(live.find_similar.find_similar_videos("not a video id!"))
        assert err.value.code == ErrorCode.INVALID_VIDEO_ID
        assert _used(live) == before  # FR-1.2: nothing was spent


# mark: FR-1.5, FR-1.6, FR-1.9, FR-5.7
class TestLiveSimilarity:
    def test_find_similar_is_ranked_excludes_seed_and_meters_quota(self, live):
        before = _used(live)
        results = run(live.find_similar.find_similar_videos(STABLE_PUBLIC_VIDEO, limit=3))
        assert 0 < len(results) <= 3
        assert all(r.video_id != STABLE_PUBLIC_VIDEO for r in results)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)
        assert _used(live) > before  # FR-5.7: the real calls were recorded


# mark: FR-3.1, FR-3.7, BR-3
class TestLiveUserLibrary:
    def test_analyse_states_it_is_not_watch_history(self, live):
        report = run(live.analyse.analyse(top_k=3))
        assert "error" not in report
        assert "watch history" in str(report["not_watch_history_statement"]).lower()


# mark: FR-5.8, FR-4.11, TR-6, BR-5
class TestLiveBudgetGuard:
    def test_over_budget_workflow_refused_before_first_call(self, tmp_path):
        tiny = build_live_container(tmp_path, budget=10)
        with pytest.raises(CerebraError) as err:
            run(tiny.find_similar.find_similar_videos(STABLE_PUBLIC_VIDEO))
        assert err.value.code == ErrorCode.QUOTA_BUDGET_EXCEEDED
        assert _used(tiny) == 0  # refused before any API call (BR-5)
