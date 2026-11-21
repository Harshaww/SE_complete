"""Unit tests for domain/playlist_solver.py (FR-4.1 to FR-4.3)."""

from cerebra.domain.playlist_solver import solve_playlist
from tests.conftest import make_video


def _make_videos(specs):
    """specs: list of (video_id, duration_seconds, language)"""
    return [
        make_video(
            video_id=vid_id,
            duration_seconds=dur,
            language=lang,
            title=f"Video {vid_id}",
            tags=["test"],
        )
        for vid_id, dur, lang in specs
    ]


class TestSolvePlaylist:
    def test_basic_selection(self):
        videos = _make_videos(
            [
                ("vid0001ABCDE", 600, "en"),
                ("vid0002ABCDE", 600, "en"),
                ("vid0003ABCDE", 600, "en"),
            ]
        )
        result = solve_playlist("python", 1800, videos)
        assert result.total_seconds <= 1800
        assert len(result.items) == 3
        assert result.feasible

    def test_total_does_not_exceed_requested(self):
        videos = _make_videos([(f"vid{i:07d}CDE", 400, "en") for i in range(10)])
        result = solve_playlist("topic", 1800, videos)
        assert result.total_seconds <= 1800

    def test_max_video_duration_enforced(self):
        videos = _make_videos(
            [
                ("short0ABCDE", 300, "en"),
                ("long00ABCDE", 1500, "en"),  # exceeds max
            ]
        )
        result = solve_playlist("topic", 3600, videos, max_video_duration_seconds=600)
        ids = [item.video_id for item in result.items]
        assert "long00ABCDE" not in ids
        assert "short0ABCDE" in ids

    def test_language_filter_enforced(self):
        videos = _make_videos(
            [
                ("eng000ABCDE", 600, "en"),
                ("esp000ABCDE", 600, "es"),
            ]
        )
        result = solve_playlist("topic", 1800, videos, language="en")
        ids = [item.video_id for item in result.items]
        assert "esp000ABCDE" not in ids
        assert "eng000ABCDE" in ids

    def test_no_duplicate_ids(self):
        videos = _make_videos(
            [
                ("dup0000ABCDE"[:11], 300, "en"),
                ("dup0000ABCDE"[:11], 300, "en"),  # duplicate
            ]
        )
        result = solve_playlist("topic", 3600, videos)
        ids = [item.video_id for item in result.items]
        assert len(ids) == len(set(ids))

    def test_infeasible_reports_reason(self):
        videos = _make_videos(
            [
                ("vid0001ABCDE", 300, "en"),  # only 300s available, need >= 1800*0.9=1620
            ]
        )
        result = solve_playlist("topic", total_duration_seconds=1800, candidates=videos)
        assert not result.feasible
        assert result.infeasible_reason

    def test_fill_ratio_met(self):
        """FR-4.3: total >= 90% of requested."""
        videos = _make_videos([(f"vid{i:07d}CDE", 400, "en") for i in range(5)])
        result = solve_playlist("topic", 2000, videos, fill_ratio=0.9)
        min_total = int(2000 * 0.9)
        if result.feasible:
            assert result.total_seconds >= min_total

    def test_empty_candidates_infeasible(self):
        result = solve_playlist("topic", 1800, [])
        assert not result.feasible
        assert result.total_seconds == 0
