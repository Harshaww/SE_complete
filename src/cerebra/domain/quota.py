"""Quota model – cost table, pool ledger, reservation (ADR-B, FR-5.6–5.8).

Three independent pools:
  - GENERAL: 10,000 units/day for all endpoints except search
  - SEARCH: 100 calls/day (each search.list = 100 units from general pool, 1 call from search pool)
  - WRITE: subset of GENERAL for write operations (tracked separately for visibility)

NOTE: NFR-QU-1 figures (250/400 units) are STALE — see Phase 0 recon and ADR-B.
      Actual write costs: playlists.insert=50, playlistItems.insert=50 each.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum

# Official quota costs (verified against developers.google.com/youtube/v3/determine_quota_cost)
# TBD-4: re-verify at implementation time.
QUOTA_COSTS: dict[str, int] = {
    "search.list": 100,  # from general pool + 1 call from search pool
    "videos.list": 1,
    "channels.list": 1,
    "playlistItems.list": 1,
    "playlists.list": 1,
    "subscriptions.list": 1,
    "videoCategories.list": 1,
    "playlists.insert": 50,  # write
    "playlistItems.insert": 50,  # write per item
}

DEFAULT_DAILY_BUDGET = 10_000  # general pool
DEFAULT_SEARCH_BUDGET = 100  # search calls/day
WARN_THRESHOLD = 0.80  # NFR-SA-4


class Pool(str, Enum):
    GENERAL = "general"
    SEARCH = "search"
    WRITE = "write"  # virtual sub-pool of GENERAL for write tracking


@dataclass
class PoolState:
    capacity: int
    used: int = 0
    reserved: int = 0

    @property
    def remaining(self) -> int:
        return self.capacity - self.used - self.reserved

    @property
    def utilisation(self) -> float:
        if self.capacity == 0:
            return 1.0
        return (self.used + self.reserved) / self.capacity

    def can_reserve(self, amount: int) -> bool:
        return self.remaining >= amount


class QuotaLedger:
    """Thread-safe quota ledger tracking all three pools (ADR-B).

    Construct once at composition root; inject everywhere (DIP).
    No global state.
    """

    #: Reservations are real holds on this ledger (see AdapterMeteredQuota for the live path).
    holds_reservations = True

    def __init__(
        self,
        general_budget: int = DEFAULT_DAILY_BUDGET,
        search_budget: int = DEFAULT_SEARCH_BUDGET,
    ) -> None:
        self._lock = threading.Lock()
        self._general = PoolState(capacity=general_budget)
        self._search = PoolState(capacity=search_budget)
        self._write_used = 0  # subset of general used for writes

    # ── Estimation helpers ──────────────────────────────────────────────────

    def estimate_search_workflow(
        self,
        search_calls: int = 1,
        video_fetch_count: int = 50,
        channel_fetch_count: int = 0,
    ) -> dict[str, int]:
        """Estimate cost of a read-only search workflow (FR-1 / FR-2)."""
        general = (
            search_calls * QUOTA_COSTS["search.list"]
            + video_fetch_count * QUOTA_COSTS["videos.list"]
            + channel_fetch_count * QUOTA_COSTS["channels.list"]
        )
        return {"general": general, "search": search_calls}

    def estimate_playlist_workflow(self, num_items: int) -> dict[str, int]:
        """Worst-case estimate for FR-4 write workflow (FR-4.11, ADR-B).

        Called BEFORE any API call. Uses max candidate count for worst case.
        """
        write_cost = (
            QUOTA_COSTS["playlists.insert"] + num_items * QUOTA_COSTS["playlistItems.insert"]
        )
        read_cost = (
            QUOTA_COSTS["search.list"] * 2  # up to 2 search pages
            + num_items * QUOTA_COSTS["videos.list"]
        )
        return {
            "general": read_cost + write_cost,
            "search": 2,
            "write": write_cost,
        }

    # ── Reservation ─────────────────────────────────────────────────────────

    def reserve(self, general: int = 0, search: int = 0) -> bool:
        """Atomically reserve units from both pools. Returns False if insufficient.

        (ADR-B: reserve all applicable pools atomically before network I/O)
        """
        with self._lock:
            if not self._general.can_reserve(general):
                return False
            if not self._search.can_reserve(search):
                return False
            self._general.reserved += general
            self._search.reserved += search
            return True

    def release(self, general: int = 0, search: int = 0) -> None:
        """Release a reservation (on EXPIRED/CANCELLED)."""
        with self._lock:
            self._general.reserved = max(0, self._general.reserved - general)
            self._search.reserved = max(0, self._search.reserved - search)

    def consume(self, method: str, count: int = 1) -> None:
        """Record actual usage for a method call.

        Moves from reserved → used. Tracks write operations separately.
        """
        cost = QUOTA_COSTS.get(method, 1) * count
        with self._lock:
            # Move reservation to used (best effort — may not exactly match)
            self._general.used += cost
            self._general.reserved = max(0, self._general.reserved - cost)
            if method in ("search.list",):
                self._search.used += count
                self._search.reserved = max(0, self._search.reserved - count)
            if method in ("playlists.insert", "playlistItems.insert"):
                self._write_used += cost

    def can_afford(self, general: int = 0, search: int = 0) -> bool:
        """Check (without reserving) if a workflow fits in remaining budget."""
        with self._lock:
            return self._general.can_reserve(general) and self._search.can_reserve(search)

    # ── Status ──────────────────────────────────────────────────────────────

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "general": {
                    "capacity": self._general.capacity,
                    "used": self._general.used,
                    "reserved": self._general.reserved,
                    "remaining": self._general.remaining,
                    "utilisation_pct": round(self._general.utilisation * 100, 1),
                    "warn": self._general.utilisation >= WARN_THRESHOLD,
                },
                "search": {
                    "capacity": self._search.capacity,
                    "used": self._search.used,
                    "reserved": self._search.reserved,
                    "remaining": self._search.remaining,
                    "utilisation_pct": round(self._search.utilisation * 100, 1),
                    "warn": self._search.utilisation >= WARN_THRESHOLD,
                },
                "write_units_used": self._write_used,
                "note": (
                    "NFR-QU-1 (250/400 unit targets) are stale — see ADR-B. "
                    "Actual write costs: playlists.insert=50, playlistItems.insert=50 each."
                ),
            }

    @property
    def general_remaining(self) -> int:
        with self._lock:
            return self._general.remaining

    @property
    def search_remaining(self) -> int:
        with self._lock:
            return self._search.remaining
