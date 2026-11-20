"""Composition root – the ONLY place concrete dependencies are built (DIP).

No other module imports concrete infrastructure classes directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cerebra.adapters.fixtures.fixture_adapter import (
    FixtureChannelReader,
    FixturePlaylistWriter,
    FixtureUserLibraryReader,
    FixtureVideoReader,
)
from cerebra.application.analyse import AnalyseEngagementUseCase
from cerebra.application.find_similar import FindSimilarUseCase
from cerebra.application.playlist import CreatePlaylistUseCase, ProposePlaylistUseCase
from cerebra.application.recommend import RecommendVideosUseCase
from cerebra.config import Config
from cerebra.domain.quota import QuotaLedger
from cerebra.infrastructure.clock import RealClock
from cerebra.infrastructure.persistence.sqlite_stores import (
    SQLiteAuditLog,
    SQLiteCacheStore,
    SQLiteDB,
    SQLiteProposalStore,
    SQLiteQuotaStore,
)


@dataclass
class Container:
    """All assembled use cases and shared infrastructure."""
    quota: QuotaLedger
    find_similar: FindSimilarUseCase
    recommend: RecommendVideosUseCase
    analyse: AnalyseEngagementUseCase
    propose: ProposePlaylistUseCase
    create_pl: CreatePlaylistUseCase
    is_authenticated: bool


def build_container(cfg: Config, use_fixtures: bool = True) -> Container:
    """Build the production (or fixture-based) dependency graph.

    For Phase 2–4: always uses fixture adapter in this build.
    Live adapter wired in Phase 3 behind the same ports.
    """
    cfg.ensure_data_dir()
    db = SQLiteDB(cfg.db_path)
    cache = SQLiteCacheStore(db, max_size=cfg.cache_max_size)
    proposal_store = SQLiteProposalStore(db)
    audit_log = SQLiteAuditLog(db)
    quota_store = SQLiteQuotaStore(db)
    clock = RealClock()
    quota = QuotaLedger(
        general_budget=cfg.daily_quota_budget,
        search_budget=cfg.search_quota_budget,
    )

    # Wire fixture adapter (live adapter wired in Phase 3)
    video_reader = FixtureVideoReader()
    channel_reader = FixtureChannelReader()
    user_library = FixtureUserLibraryReader()
    playlist_writer = FixturePlaylistWriter()
    is_authenticated = True  # fixture mode: always authenticated

    find_similar = FindSimilarUseCase(
        video_reader=video_reader,
        channel_reader=channel_reader,
        quota=quota,
        cache=cache,
        config=cfg,
    )
    recommend = RecommendVideosUseCase(
        video_reader=video_reader,
        user_library=user_library,
        quota=quota,
        cache=cache,
        config=cfg,
        is_authenticated=is_authenticated,
    )
    analyse = AnalyseEngagementUseCase(
        user_library=user_library,
        quota=quota,
        cache=cache,
        config=cfg,
        is_authenticated=is_authenticated,
    )
    propose = ProposePlaylistUseCase(
        video_reader=video_reader,
        quota=quota,
        proposal_store=proposal_store,
        cache=cache,
        clock=clock,
        config=cfg,
        is_authenticated=is_authenticated,
    )
    create_pl = CreatePlaylistUseCase(
        playlist_writer=playlist_writer,
        quota=quota,
        proposal_store=proposal_store,
        audit_log=audit_log,
        clock=clock,
        config=cfg,
    )

    return Container(
        quota=quota,
        find_similar=find_similar,
        recommend=recommend,
        analyse=analyse,
        propose=propose,
        create_pl=create_pl,
        is_authenticated=is_authenticated,
    )
