"""Builds a fully wired LIVE container (real composition root, real OAuthManager, real
SQLite) on top of the in-memory YouTube double. No network, no secrets."""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from cerebra.cli import main as cli_main
from cerebra.config import Config
from cerebra.domain.entities import ChannelMetadata, VideoMetadata
from cerebra.infrastructure.auth.oauth_manager import SCOPE_READONLY, SCOPE_WRITE, OAuthManager
from cerebra.infrastructure.auth.token_store import InMemoryTokenStore
from cerebra.infrastructure.clock import FakeClock
from cerebra.infrastructure.composition import Container, build_container
from tests.support.fake_youtube import FakeYouTube

NOW = 1_800_000_000.0
CHANNEL = "UCuAXFkgsw1L7xaCfnd5JJOw"


def token_record(scopes=(SCOPE_READONLY, SCOPE_WRITE), authorised_at=NOW):
    return {
        "credentials": {
            "token": "ya29.fake", "refresh_token": "1//r", "client_id": "cid",
            "client_secret": "csecret", "scopes": list(scopes),
            "token_uri": "https://oauth2.googleapis.com/token",
            "expiry": "2099-01-01T00:00:00Z",
        },
        "scopes": list(scopes), "authorised_at": authorised_at,
    }


def python_catalog(n: int = 8, seconds: int = 300) -> list[VideoMetadata]:
    return [
        VideoMetadata(f"pyvid{i:06d}", f"Python tutorial part {i}", "learn python", CHANNEL,
                      "Py Channel", seconds, "27", "en", ["python"], False, "", "2024-01-01T00:00:00Z")
        for i in range(n)
    ]


def py_channel() -> ChannelMetadata:
    return ChannelMetadata(CHANNEL, "Py Channel", "python lessons", ["python"], ["Technology"], "en", 1000)


@dataclass
class LiveEnv:
    container: Container
    fake: FakeYouTube
    oauth: OAuthManager
    store: InMemoryTokenStore
    cfg: Config
    clock: FakeClock

    def propose(self, topic: str = "python", total: int = 900) -> dict[str, Any]:
        from tests.support.helpers import run
        return run(self.container.propose.propose(topic, total))

    def approve(self, proposal_id: str, typed: Optional[str] = None, tty: bool = True) -> tuple[int, str, str]:
        p = self.container.proposal_store.load(proposal_id)
        out, err = io.StringIO(), io.StringIO()
        code = cli_main(
            ["approve", proposal_id], container_factory=lambda: self.container,
            input_fn=lambda prompt: (typed if typed is not None else (p.digest[:8] if p else "")),
            isatty=lambda: tty, out=out, err=err,
        )
        return code, out.getvalue(), err.getvalue()

    def create(self, proposal_id: str, digest: str, privacy: str = "private") -> dict[str, Any]:
        from tests.support.helpers import run
        return run(self.container.create_pl.create(proposal_id, digest, privacy))


def make_env(
    tmp_path: Path,
    fake: Optional[FakeYouTube] = None,
    *,
    scopes=(SCOPE_READONLY, SCOPE_WRITE),
    token: bool = True,
    interactive: bool = False,
    flow_factory: Any = None,
    budget: int = 10_000,
    clock: Optional[FakeClock] = None,
) -> LiveEnv:
    fake = fake or FakeYouTube(python_catalog(), [py_channel()])
    cfg = Config()
    cfg.data_dir = tmp_path / "cerebra"
    cfg.daily_quota_budget = budget
    cfg.search_quota_budget = 100
    cfg.token_file = tmp_path / "token.json"
    cfg.use_keyring = False
    clock = clock or FakeClock(NOW)
    store = InMemoryTokenStore()
    if token:
        store.save_token(token_record(scopes))
    oauth = OAuthManager(store, "cid", "csecret", clock, interactive=interactive,
                         flow_factory=flow_factory, stderr=io.StringIO())
    container = build_container(
        cfg, use_fixtures=False, oauth=oauth,
        service_factory=lambda creds, key: fake, clock=clock,
    )
    return LiveEnv(container, fake, oauth, store, cfg, clock)
