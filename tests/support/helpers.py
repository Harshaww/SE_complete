"""Shared test helpers (no global event-loop state is touched)."""
from __future__ import annotations

import asyncio
from typing import Any, Coroutine, Optional, TypeVar

from cerebra.adapters.youtube.live_adapter import LiveYouTubeAdapter
from cerebra.domain.quota import QuotaLedger
from cerebra.infrastructure.clock import FakeClock
from tests.support.fake_youtube import FakeYouTube

T = TypeVar("T")


def run(coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine on a private loop so other tests' loop handling is unaffected."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeCreds:
    token = "fake-access-token"  # noqa: S105 - test double, not a credential


class FakeAuth:
    """AuthProvider double. Records which scopes were requested."""

    def __init__(self, authenticated: bool = True) -> None:
        self.authenticated = authenticated
        self.scopes_requested: list[str] = []
        self.ensure_scope_calls: list[str] = []

    def is_authenticated(self) -> bool:
        return self.authenticated

    def get_credentials(self, required_scope: str = "") -> FakeCreds:
        self.scopes_requested.append(required_scope)
        return FakeCreds()

    def ensure_scope(self, scope: str) -> FakeCreds:
        self.ensure_scope_calls.append(scope)
        return FakeCreds()


class NoSleep:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def make_live(
    fake: FakeYouTube,
    *,
    quota: Optional[QuotaLedger] = None,
    auth: Optional[FakeAuth] = None,
    api_key: str = "",
    sleep: Optional[NoSleep] = None,
) -> tuple[LiveYouTubeAdapter, QuotaLedger, FakeAuth, NoSleep]:
    q = quota or QuotaLedger(general_budget=10_000, search_budget=100)
    a = auth if auth is not None else FakeAuth()
    s = sleep or NoSleep()
    adapter = LiveYouTubeAdapter(
        q, FakeClock(timestamp=1_700_000_000.0), a, api_key=api_key,
        service_factory=lambda creds, key: fake, sleep=s, backoff_base_s=0.5,
    )
    return adapter, q, a, s
