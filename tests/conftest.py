"""conftest.py – shared fixtures for all test layers."""
from __future__ import annotations

import pytest

from cerebra.adapters.fixtures.fixture_adapter import (
    FixtureChannelReader,
    FixturePlaylistWriter,
    FixtureUserLibraryReader,
    FixtureVideoReader,
    _dict_to_channel,
    _dict_to_video,
)
from cerebra.config import Config
from cerebra.domain.entities import ChannelMetadata, VideoMetadata
from cerebra.domain.quota import QuotaLedger
from cerebra.infrastructure.clock import FakeClock
from cerebra.infrastructure.persistence.sqlite_stores import (
    SQLiteAuditLog,
    SQLiteCacheStore,
    SQLiteDB,
    SQLiteProposalStore,
)


# ── Helper builders ────────────────────────────────────────────────────────────

def make_video(**kwargs: object) -> VideoMetadata:
    defaults = {
        "video_id": "dQw4w9WgXcQ",
        "title": "Test Video",
        "description": "A test description about machine learning and Python",
        "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "channel_title": "Test Channel",
        "duration_seconds": 600,
        "category_id": "27",
        "language": "en",
        "tags": ["python", "machine learning", "tutorial"],
        "tags_missing": False,
        "published_at": "2024-01-15T10:00:00Z",
    }
    defaults.update(kwargs)
    return VideoMetadata(**defaults)  # type: ignore[arg-type]


def make_channel(**kwargs: object) -> ChannelMetadata:
    defaults = {
        "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "title": "Test Channel",
        "description": "A channel about Python and machine learning",
        "keywords": ["python", "machine learning"],
        "topic_categories": ["Technology"],
        "language": "en",
        "subscriber_count": 100000,
        "upload_cadence_per_month": 4.0,
        "recent_upload_titles": ["Python tutorial", "ML basics"],
    }
    defaults.update(kwargs)
    return ChannelMetadata(**defaults)  # type: ignore[arg-type]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def config(tmp_path):
    cfg = Config()
    cfg.data_dir = tmp_path / "cerebra"
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.daily_quota_budget = 10000
    cfg.search_quota_budget = 100
    cfg.cache_ttl_seconds = 300
    cfg.proposal_expiry_seconds = 900
    return cfg


@pytest.fixture
def quota():
    return QuotaLedger(general_budget=10000, search_budget=100)


@pytest.fixture
def db(tmp_path):
    return SQLiteDB(tmp_path / "test.db")


@pytest.fixture
def cache(db):
    return SQLiteCacheStore(db, max_size=100)


@pytest.fixture
def proposal_store(db):
    return SQLiteProposalStore(db)


@pytest.fixture
def audit_log(db):
    return SQLiteAuditLog(db)


@pytest.fixture
def clock():
    return FakeClock(timestamp=1700000000.0)


@pytest.fixture
def video_reader():
    r = FixtureVideoReader.__new__(FixtureVideoReader)
    r._videos = {}
    return r


@pytest.fixture
def channel_reader():
    r = FixtureChannelReader.__new__(FixtureChannelReader)
    r._channels = {}
    r._handles = {}
    return r


@pytest.fixture
def user_library():
    r = FixtureUserLibraryReader.__new__(FixtureUserLibraryReader)
    r._liked = []
    r._subscriptions = []
    r._playlists = []
    r._playlist_items = {}
    return r


@pytest.fixture
def playlist_writer():
    return FixturePlaylistWriter()


@pytest.fixture
def sample_video():
    return make_video()


@pytest.fixture
def sample_channel():
    return make_channel()
