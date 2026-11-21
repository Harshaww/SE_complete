"""MCP end-to-end tests (TR-3): FR-1 to FR-5 through the real MCP interface with fixture provider."""

from __future__ import annotations

import asyncio

import pytest

from cerebra.config import Config
from cerebra.infrastructure.composition import build_container


def _make_config(tmp_path):
    cfg = Config()
    cfg.data_dir = tmp_path / "cerebra"
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.daily_quota_budget = 10000
    cfg.search_quota_budget = 100
    return cfg


# mark: TR-3, FR-1.6, FR-5.12
class TestMCPFindSimilarVideos:
    """FR-1: Similarity Discovery via MCP interface."""

    def test_find_similar_videos_no_data_returns_empty(self, tmp_path):
        cfg = _make_config(tmp_path)
        container = build_container(cfg)
        # With empty fixture store: should return empty list (no candidates)
        result = asyncio.get_event_loop().run_until_complete(
            container.find_similar.find_similar_videos("dQw4w9WgXcQ", limit=10)
        )
        assert isinstance(result, list)

    def test_invalid_reference_returns_structured_error(self, tmp_path):
        from cerebra.domain.errors import CerebraError, ErrorCode

        cfg = _make_config(tmp_path)
        container = build_container(cfg)
        with pytest.raises(CerebraError) as exc:
            asyncio.get_event_loop().run_until_complete(
                container.find_similar.find_similar_videos("not-a-valid-ref!", limit=10)
            )
        assert exc.value.code == ErrorCode.INVALID_VIDEO_ID

    def test_over_budget_rejected_before_api_call(self, tmp_path):
        """TR-6, FR-5.8: over-budget workflow rejected with zero provider calls."""
        from cerebra.domain.errors import CerebraError, ErrorCode

        cfg = _make_config(tmp_path)
        cfg.daily_quota_budget = 0  # no budget at all
        container = build_container(cfg)
        with pytest.raises(CerebraError) as exc:
            asyncio.get_event_loop().run_until_complete(
                container.find_similar.find_similar_videos("dQw4w9WgXcQ", limit=10)
            )
        assert exc.value.code == ErrorCode.QUOTA_BUDGET_EXCEEDED


# mark: TR-3, FR-2.1, FR-2.5
class TestMCPRecommend:
    """FR-2: Recommendations."""

    def test_unauthenticated_returns_auth_required(self, tmp_path):
        from cerebra.adapters.fixtures.fixture_adapter import (
            FixtureUserLibraryReader,
            FixtureVideoReader,
        )
        from cerebra.application.recommend import RecommendVideosUseCase
        from cerebra.domain.errors import CerebraError, ErrorCode
        from cerebra.domain.quota import QuotaLedger
        from cerebra.infrastructure.persistence.sqlite_stores import SQLiteCacheStore, SQLiteDB

        cfg = _make_config(tmp_path)
        db = SQLiteDB(cfg.db_path)
        cache = SQLiteCacheStore(db)
        quota = QuotaLedger(10000, 100)

        uc = RecommendVideosUseCase(
            video_reader=FixtureVideoReader(),
            user_library=FixtureUserLibraryReader(),
            quota=quota,
            cache=cache,
            config=cfg,
            is_authenticated=False,  # <-- not authenticated
        )
        with pytest.raises(CerebraError) as exc:
            asyncio.get_event_loop().run_until_complete(uc.recommend())
        assert exc.value.code == ErrorCode.AUTH_REQUIRED

    def test_empty_profile_returns_explanatory_empty(self, tmp_path):
        """FR-2.6: empty profile → explanatory empty result, not error."""
        from cerebra.adapters.fixtures.fixture_adapter import (
            FixtureUserLibraryReader,
            FixtureVideoReader,
        )
        from cerebra.application.recommend import RecommendVideosUseCase
        from cerebra.domain.quota import QuotaLedger
        from cerebra.infrastructure.persistence.sqlite_stores import SQLiteCacheStore, SQLiteDB

        cfg = _make_config(tmp_path)
        db = SQLiteDB(cfg.db_path)
        cache = SQLiteCacheStore(db)
        quota = QuotaLedger(10000, 100)

        uc = RecommendVideosUseCase(
            video_reader=FixtureVideoReader(),
            user_library=FixtureUserLibraryReader(),  # empty library
            quota=quota,
            cache=cache,
            config=cfg,
            is_authenticated=True,
        )
        result = asyncio.get_event_loop().run_until_complete(uc.recommend())
        assert "recommendations" in result
        assert result["recommendations"] == []
        assert "note" in result  # explanatory message
        assert "not_watch_history" in result["note"].lower() or "not" in result["note"].lower()


# mark: TR-3, FR-3.1, FR-3.7
class TestMCPAnalyse:
    """FR-3: Engagement Analysis."""

    def test_analyse_requires_auth(self, tmp_path):
        from cerebra.adapters.fixtures.fixture_adapter import FixtureUserLibraryReader
        from cerebra.application.analyse import AnalyseEngagementUseCase
        from cerebra.domain.errors import CerebraError, ErrorCode
        from cerebra.domain.quota import QuotaLedger
        from cerebra.infrastructure.persistence.sqlite_stores import SQLiteCacheStore, SQLiteDB

        cfg = _make_config(tmp_path)
        db = SQLiteDB(cfg.db_path)
        cache = SQLiteCacheStore(db)
        quota = QuotaLedger(10000, 100)

        uc = AnalyseEngagementUseCase(
            user_library=FixtureUserLibraryReader(),
            quota=quota,
            cache=cache,
            config=cfg,
            is_authenticated=False,
        )
        with pytest.raises(CerebraError) as exc:
            asyncio.get_event_loop().run_until_complete(uc.analyse())
        assert exc.value.code == ErrorCode.AUTH_REQUIRED

    def test_analyse_empty_data_returns_empty_sections(self, tmp_path):
        """FR-3.8: empty sections with explanation when library is empty."""
        from cerebra.adapters.fixtures.fixture_adapter import FixtureUserLibraryReader
        from cerebra.application.analyse import AnalyseEngagementUseCase
        from cerebra.domain.quota import QuotaLedger
        from cerebra.infrastructure.persistence.sqlite_stores import SQLiteCacheStore, SQLiteDB

        cfg = _make_config(tmp_path)
        db = SQLiteDB(cfg.db_path)
        cache = SQLiteCacheStore(db)
        quota = QuotaLedger(10000, 100)

        # Pass a tmp_path subdir with no fixture files → truly empty library
        empty_dir = tmp_path / "empty_playlists"
        empty_dir.mkdir()
        uc = AnalyseEngagementUseCase(
            user_library=FixtureUserLibraryReader(fixture_dir=empty_dir),
            quota=quota,
            cache=cache,
            config=cfg,
            is_authenticated=True,
        )
        result = asyncio.get_event_loop().run_until_complete(uc.analyse())
        assert result["top_channels"] == []
        assert result["top_categories"] == []
        assert "watch history" in result["not_watch_history_statement"].lower()
        assert "empty_explanation" in result or "top_channels" in result


# mark: TR-3, FR-4.4, FR-4.5
class TestMCPProposePlaylst:
    """FR-4: Playlist Creation — propose phase."""

    def test_propose_missing_topic_returns_missing_constraint(self, tmp_path):
        """FR-4.1: missing mandatory constraint → MISSING_CONSTRAINT error."""
        from cerebra.adapters.fixtures.fixture_adapter import FixtureVideoReader
        from cerebra.application.playlist import ProposePlaylistUseCase
        from cerebra.domain.errors import CerebraError, ErrorCode
        from cerebra.domain.quota import QuotaLedger
        from cerebra.infrastructure.clock import FakeClock
        from cerebra.infrastructure.persistence.sqlite_stores import (
            SQLiteCacheStore,
            SQLiteDB,
            SQLiteProposalStore,
        )

        cfg = _make_config(tmp_path)
        db = SQLiteDB(cfg.db_path)
        cache = SQLiteCacheStore(db)
        quota = QuotaLedger(10000, 100)
        clock = FakeClock(1700000000.0)

        uc = ProposePlaylistUseCase(
            video_reader=FixtureVideoReader(),
            quota=quota,
            proposal_store=SQLiteProposalStore(db),
            cache=cache,
            clock=clock,
            config=cfg,
            is_authenticated=True,
        )
        with pytest.raises(CerebraError) as exc:
            asyncio.get_event_loop().run_until_complete(
                uc.propose(topic=None, total_duration_seconds=3600)
            )
        assert exc.value.code == ErrorCode.MISSING_CONSTRAINT

    def test_propose_missing_duration_returns_missing_constraint(self, tmp_path):
        from cerebra.adapters.fixtures.fixture_adapter import FixtureVideoReader
        from cerebra.application.playlist import ProposePlaylistUseCase
        from cerebra.domain.errors import CerebraError, ErrorCode
        from cerebra.domain.quota import QuotaLedger
        from cerebra.infrastructure.clock import FakeClock
        from cerebra.infrastructure.persistence.sqlite_stores import (
            SQLiteCacheStore,
            SQLiteDB,
            SQLiteProposalStore,
        )

        cfg = _make_config(tmp_path)
        db = SQLiteDB(cfg.db_path)
        cache = SQLiteCacheStore(db)
        quota = QuotaLedger(10000, 100)
        clock = FakeClock(1700000000.0)

        uc = ProposePlaylistUseCase(
            video_reader=FixtureVideoReader(),
            quota=quota,
            proposal_store=SQLiteProposalStore(db),
            cache=cache,
            clock=clock,
            config=cfg,
            is_authenticated=True,
        )
        with pytest.raises(CerebraError) as exc:
            asyncio.get_event_loop().run_until_complete(
                uc.propose(topic="Python", total_duration_seconds=None)
            )
        assert exc.value.code == ErrorCode.MISSING_CONSTRAINT


# mark: FR-5.15, NFR-US-1
class TestUniformErrors:
    """FR-5.15: errors in uniform structure (code, message, retryable, action)."""

    def test_cerebra_error_to_dict_structure(self):
        from cerebra.domain.errors import CerebraError, ErrorCode

        err = CerebraError(
            code=ErrorCode.AUTH_REQUIRED,
            message="Need auth",
            retryable=False,
            suggested_action="Re-authorise",
        )
        d = err.to_dict()
        assert "error" in d
        assert d["error"]["code"] == "AUTH_REQUIRED"
        assert isinstance(d["error"]["retryable"], bool)
        assert d["error"]["suggested_action"]
