"""Cerebra server configuration (FR-5.11, TBD-2 through TBD-9)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Base data directory
_DEFAULT_DATA_DIR = Path.home() / ".cerebra"


def _default_token_file() -> Path:
    """Owner-only fallback token file (ADR-D §3): ~/.config/cerebra/token.json."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "cerebra" / "token.json"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


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

    # Optional API key for PUBLIC reads when no OAuth token exists (env only, never in code).
    youtube_api_key: str = field(
        default_factory=lambda: os.environ.get("CEREBRA_YOUTUBE_API_KEY", "")
    )

    # Adapter selection (NFR-TE-1: CI sets CEREBRA_USE_FIXTURES=1; live is the default).
    use_fixtures: bool = field(default_factory=lambda: _env_flag("CEREBRA_USE_FIXTURES", False))

    # Token storage (ADR-D §3): OS keyring preferred, owner-only file fallback.
    token_file: Path = field(
        default_factory=lambda: Path(
            os.environ.get("CEREBRA_TOKEN_FILE", str(_default_token_file()))
        )
    )
    use_keyring: bool = field(default_factory=lambda: _env_flag("CEREBRA_USE_KEYRING", True))

    # Allow the server to start the browser consent flow itself when create_playlist
    # needs the `youtube` scope (FR-5.1). If False, it fails with INSUFFICIENT_SCOPE and
    # tells the human to run `cerebra-cli login --write`.
    interactive_auth: bool = field(default_factory=lambda: _env_flag("CEREBRA_INTERACTIVE_AUTH", True))

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
        return self.token_file

    def ensure_data_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


def get_config() -> Config:
    """Return a Config instance built from environment variables."""
    return Config()
