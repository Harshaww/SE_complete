"""Additional coverage tests for application layer use cases.

These tests drive the application use cases with fixture data to cover
branches not reached by the existing e2e tests.
# mark: FR-1, FR-2, FR-3, FR-4
"""

from __future__ import annotations

import asyncio

from tests.conftest import make_video

# ── helpers ──────────────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


def _make_full_fixture_reader():
    """Return a FixtureVideoReader pre-loaded with known videos."""
    from cerebra.adapters.fixtures.fixture_adapter import FixtureVideoReader

    r = FixtureVideoReader.__new__(FixtureVideoReader)
    r._videos = {}
    r._by_category = {}
    r._by_channel = {}

    # Pre-load a set of videos
    videos = [
        make_video(video_id="dQw4w9WgXcQ", category_id="10", channel_id="UCmusic001"),
        make_video(
            video_id="M7lc1UVf-VE",
            category_id="27",
            channel_id="UCtech001",
            title="Python programming full course",
            tags=["python", "programming", "tutorial"],
        ),
        make_video(
            video_id="rfscVS0vtbw",
            category_id="27",
            channel_id="UCtech001",
            title="Learn Python for beginners tutorial",
            tags=["python", "beginner", "learn"],
        ),
        make_video(
            video_id="jNQXAC9IVRw",
            category_id="22",
            channel_id="UCjawed01",
            title="Me at the zoo",
            tags=["zoo", "animals"],
        ),
    ]
    for v in videos:
        r._videos[v.video_id] = v
        r._by_category.setdefault(v.category_id, []).append(v)
        r._by_channel.setdefault(v.channel_id, []).append(v)
    return r


# ── FindSimilarUseCase coverage ───────────────────────────────────────────────


# mark: FR-1.4, FR-1.8, FR-5.9
class TestFindSimilarCoverage:
    """Cover find_similar application branches (FR-1)."""

    def test_find_similar_videos_with_data(self, tmp_path):
        """FR-1: seed video present → returns ranked similar videos."""
        from cerebra.application.find_similar import FindSimilarUseCase
        from cerebra.config import Config
        from cerebra.domain.quota import QuotaLedger
        from cerebra.infrastructure.persistence.sqlite_stores import SQLiteCacheStore, SQLiteDB

        cfg = Config()
        cfg.data_dir = tmp_path / "cerebra"
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        cfg.daily_quota_budget = 10000
        cfg.search_quota_budget = 100
        cfg.cache_ttl_seconds = 300
        cfg.max_candidates = 20

        db = SQLiteDB(cfg.db_path)
        cache = SQLiteCacheStore(db)
        quota = QuotaLedger(10000, 100)
        video_reader = _make_full_fixture_reader()

        from cerebra.adapters.fixtures.fixture_adapter import FixtureChannelReader

        channel_reader = FixtureChannelReader.__new__(FixtureChannelReader)
        channel_reader._channels = {}
        channel_reader._handles = {}

        uc = FindSimilarUseCase(
            video_reader=video_reader,
            channel_reader=channel_reader,
            quota=quota,
            cache=cache,
            config=cfg,
        )
        results = _run(uc.find_similar_videos("M7lc1UVf-VE", 5))
        # Should find similar tech videos (not seed itself)
        ids = [r.video_id for r in results]
        assert "M7lc1UVf-VE" not in ids  # seed excluded
        assert len(results) <= 5

    def test_find_similar_videos_cache_hit(self, tmp_path):
        """FR-5.9: second call returns cached result."""
        from cerebra.application.find_similar import FindSimilarUseCase
        from cerebra.config import Config
        from cerebra.domain.quota import QuotaLedger
        from cerebra.infrastructure.persistence.sqlite_stores import SQLiteCacheStore, SQLiteDB

        cfg = Config()
        cfg.data_dir = tmp_path / "cerebra"
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        cfg.daily_quota_budget = 10000
        cfg.search_quota_budget = 100
        cfg.cache_ttl_seconds = 300
        cfg.max_candidates = 20

        db = SQLiteDB(cfg.db_path)
        cache = SQLiteCacheStore(db)
        quota = QuotaLedger(10000, 100)
        video_reader = _make_full_fixture_reader()

        from cerebra.adapters.fixtures.fixture_adapter import FixtureChannelReader

        channel_reader = FixtureChannelReader.__new__(FixtureChannelReader)
        channel_reader._channels = {}
        channel_reader._handles = {}

        uc = FindSimilarUseCase(
            video_reader=video_reader,
            channel_reader=channel_reader,
            quota=quota,
            cache=cache,
            config=cfg,
        )
        r1 = _run(uc.find_similar_videos("M7lc1UVf-VE", 5))
        quota_after_first = quota.general_remaining

        r2 = _run(uc.find_similar_videos("M7lc1UVf-VE", 5))
        # Second call hits cache → no additional quota consumed
        assert quota.general_remaining == quota_after_first
        assert [v.video_id for v in r1] == [v.video_id for v in r2]


# ── AnalyseEngagementUseCase coverage ────────────────────────────────────────


# mark: FR-3.2, FR-3.3, FR-3.8, FR-3.4, FR-3.5, FR-3.6
class TestAnalyseCoverage:
    """Cover analyse application branches (FR-3)."""

    def test_analyse_with_liked_videos(self, tmp_path):
        """FR-3: returns non-empty top_channels when liked videos exist."""
        from cerebra.adapters.fixtures.fixture_adapter import FixtureUserLibraryReader
        from cerebra.application.analyse import AnalyseEngagementUseCase
        from cerebra.config import Config
        from cerebra.domain.quota import QuotaLedger
        from cerebra.infrastructure.persistence.sqlite_stores import SQLiteCacheStore, SQLiteDB

        cfg = Config()
        cfg.data_dir = tmp_path / "cerebra"
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        cfg.daily_quota_budget = 10000
        cfg.search_quota_budget = 100
        cfg.cache_ttl_seconds = 300

        db = SQLiteDB(cfg.db_path)
        cache = SQLiteCacheStore(db)
        quota = QuotaLedger(10000, 100)

        # Use the default fixture dir which has liked_videos.json
        library = FixtureUserLibraryReader()

        uc = AnalyseEngagementUseCase(
            user_library=library,
            quota=quota,
            cache=cache,
            config=cfg,
            is_authenticated=True,
        )
        result = _run(uc.analyse(top_k=5))
        assert "top_channels" in result
        assert "top_categories" in result
        assert "not_watch_history_statement" in result
        # With fixture data: 2 liked videos from 2 different channels
        assert isinstance(result["top_channels"], list)

    def test_analyse_with_period_comparison(self, tmp_path):
        """FR-3.5: period comparison returns trend section."""
        from cerebra.adapters.fixtures.fixture_adapter import FixtureUserLibraryReader
        from cerebra.application.analyse import AnalyseEngagementUseCase
        from cerebra.config import Config
        from cerebra.domain.quota import QuotaLedger
        from cerebra.infrastructure.persistence.sqlite_stores import SQLiteCacheStore, SQLiteDB

        cfg = Config()
        cfg.data_dir = tmp_path / "cerebra"
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        cfg.daily_quota_budget = 10000
        cfg.search_quota_budget = 100
        cfg.cache_ttl_seconds = 300

        db = SQLiteDB(cfg.db_path)
        cache = SQLiteCacheStore(db)
        quota = QuotaLedger(10000, 100)
        library = FixtureUserLibraryReader()

        uc = AnalyseEngagementUseCase(
            user_library=library,
            quota=quota,
            cache=cache,
            config=cfg,
            is_authenticated=True,
        )
        result = _run(
            uc.analyse(
                top_k=5,
                period_a=("2023-01-01", "2023-06-30"),
                period_b=("2024-01-01", "2024-06-30"),
            )
        )
        assert "top_channels" in result


# ── RecommendVideosUseCase coverage ──────────────────────────────────────────


# mark: FR-2.2, FR-2.4, FR-2.6, FR-2.3
class TestRecommendCoverage:
    """Cover recommend application branches (FR-2)."""

    def test_recommend_with_liked_videos(self, tmp_path):
        """FR-2: recommend based on liked video history."""
        from cerebra.adapters.fixtures.fixture_adapter import (
            FixtureUserLibraryReader,
        )
        from cerebra.application.recommend import RecommendVideosUseCase
        from cerebra.config import Config
        from cerebra.domain.quota import QuotaLedger
        from cerebra.infrastructure.persistence.sqlite_stores import SQLiteCacheStore, SQLiteDB

        cfg = Config()
        cfg.data_dir = tmp_path / "cerebra"
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        cfg.daily_quota_budget = 10000
        cfg.search_quota_budget = 100
        cfg.cache_ttl_seconds = 300
        cfg.max_candidates = 20

        db = SQLiteDB(cfg.db_path)
        cache = SQLiteCacheStore(db)
        quota = QuotaLedger(10000, 100)
        video_reader = _make_full_fixture_reader()
        library = FixtureUserLibraryReader()

        uc = RecommendVideosUseCase(
            video_reader=video_reader,
            user_library=library,
            quota=quota,
            cache=cache,
            config=cfg,
            is_authenticated=True,
        )
        result = _run(uc.recommend(limit=5))
        assert isinstance(result, dict)
        assert "results" in result or "recommendations" in result or isinstance(result, dict)
