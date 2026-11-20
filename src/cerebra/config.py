"""Cerebra server configuration (FR-5.11, TBD-2 through TBD-9)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Base data directory
_DEFAULT_DATA_DIR = Path.home() / ".cerebra"


@dataclass
class Config:
    """All configuration in one place. Read from env vars; no secrets in code (FR-5.2)."""

    # Quota
    daily_quota_budget: int = int(os.environ.get("CEREBRA_QUOTA_BUDGET", "10000"))
    search_quota_budget: int = int(os.environ.get("CEREBRA_SEARCH_BUDGET", "100"))
    quota_warn_threshold: float = float(os.environ.get("CEREBRA_QUOTA_WARN", "0.80"))

    # Cache
    cache_ttl_seconds: int = int(os.environ.get("CEREBRA_CACHE_TTL", "3600"))
    cache_max_size: int = int(os.environ.get("CEREBRA_CACHE_MAX", "1000"))
    cache_retention_days: int = int(os.environ.get("CEREBRA_CACHE_RETAIN_DAYS", "7"))

    # Proposal
    proposal_expiry_seconds: int = int(os.environ.get("CEREBRA_PROPOSAL_EXPIRY", "900"))  # 15 min

    # Similarity / results
    max_candidates: int = int(os.environ.get("CEREBRA_MAX_CANDIDATES", "200"))
    default_result_limit: int = 10   # FR-1.7
    max_result_limit: int = 50       # FR-1.7

    # Duration bands (TBD-7)
    band_short_max_seconds: int = 240   # < 4 min
    band_medium_max_seconds: int = 1200  # 4–20 min

    # Playlist fill ratio (TBD-8)
    playlist_fill_ratio: float = 0.90

    # OAuth (TBD-10) — IDs from env, never from source
    google_client_id: str = field(
        default_factory=lambda: os.environ.get("GOOGLE_CLIENT_ID", "")
    )
    google_client_secret: str = field(
        default_factory=lambda: os.environ.get("GOOGLE_CLIENT_SECRET", "")
    )

    # Storage
    data_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("CEREBRA_DATA_DIR", str(_DEFAULT_DATA_DIR))
        )
    )

    # MCP transport (TBD-5): stdio only for Phases 2–4
    transport: str = os.environ.get("CEREBRA_TRANSPORT", "stdio")

    # Liked-video cap disclosure
    liked_video_cap_note: str = (
        "Based on up to 1,000 most recently liked videos accessible via the YouTube API; "
        "complete like history is not available from the API."
    )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "cerebra.db"

    @property
    def token_path(self) -> Path:
        return self.data_dir / "token.json"

    def ensure_data_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


def get_config() -> Config:
    """Return a Config instance built from environment variables."""
    return Config()
