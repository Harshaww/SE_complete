# ADR-B: Quota Model + Reservation Lifecycle

**Status:** Accepted  
**Date:** 2026-11-09  
**Deciders:** SegmentationFault team  
**SRS refs:** NFR-QU-1, FR-1.4, FR-5.8, FR-4.11, BR-5, TBD-4
**Brain notes:** [Quota notes](../../brain/resources/youtube-api/quota-notes.md)  

---

## Context

The YouTube Data API v3 quota system (verified against [official quota page](https://developers.google.com/youtube/v3/getting-started#quota) on 2026-11-09) operates as follows:

| Pool | Default daily limit | Reset |
|------|--------------------|----|
| General units | 10,000 units/day | Midnight Pacific Time |
| `search.list` calls | 100 calls/day (separate bucket, 100 units each = up to 10,000 units) | Midnight Pacific Time |
| `videos.insert` calls | 100 calls/day (separate bucket) | Midnight Pacific Time |

Key unit costs (verified):

| Operation | Cost |
|-----------|-----|
| `videos.list` | 1 unit |
| `channels.list` | 1 unit |
| `playlistItems.list` | 1 unit |
| `search.list` | 100 units |
| `playlists.insert` | 50 units |
| `playlistItems.insert` | 50 units per item |
| Invalid requests | ≥ 1 unit (may be charged) |
| Each additional page | Same cost as first page |

> [!WARNING]
> **SRS NFR-QU-1 figure is STALE.** The SRS assumes ~250 units per FR-1 workflow using `search.list`-based candidate generation. With `search.list` limited to **100 calls/day** (a separate pool), a system using `search.list` as primary discovery hits this limit after 100 searches — independent of the 10,000-unit general pool. This renders the SRS's 40 FR-1 workflows/day target unreachable if search is used for every candidate fetch.

**Corrected approach (C-1):** Prefer `videos.list` / `channels.list` / `playlistItems.list` (1 unit each) for candidate retrieval. Reserve `search.list` as a scarce, explicitly budgeted resource. Corrected estimate: FR-1 without search ≈ 20–50 general units; FR-4 with 10-video playlist ≈ 50 (playlists.insert) + 500 (10 × playlistItems.insert) = 550 write units.

---

## Decision

### 1. Three-Pool Model

```python
class QuotaLedger:
    general_budget: int    # default 10_000 units/day
    search_budget: int     # default 100 calls/day (separate pool)
    write_budget: int      # derived: playlists.insert + playlistItems.insert budget
```

Each pool tracked independently. `QuotaLedger` is in-memory and thread-safe (threading.Lock). Persistent high-watermark stored in `SQLiteQuotaStore` for cross-restart accounting.

### 2. Upfront Estimation Before Any I/O (FR-5.8, BR-5)

Before the first network call in any workflow:

1. Estimate **worst-case** units for the entire workflow (search pages + candidate fetch + write operations)
2. Reserve all required units across all applicable pools atomically
3. If any pool cannot accommodate the reservation → `QUOTA_EXCEEDED` error, **zero** API calls made

```python
# Example: propose_playlist with 10 candidates, no search
estimate = QuotaEstimate(
    general=10 * 1,   # videos.list for candidates
    search=0,         # no search.list used
    write=50 + 10*50, # playlists.insert + 10 × playlistItems.insert
)
quota.reserve(estimate)  # atomic; raises if any pool overflows
```

### 3. Reservation Lifecycle

```
propose_playlist called
  → estimate computed
  → reservation HELD (all pools decremented)
  → proposal stored with reservation_id
  → proposal in PROPOSED state (15-minute window)
  
  On EXPIRED or CANCELLED:
    → reservation RELEASED (units returned)
  
  On create_playlist confirmed:
    → actual units consumed tracked
    → reconcile: if actual < estimate, return surplus
    → if actual > estimate (extra pages), log WARNING (over-budget guard)
```

> [!NOTE]
> Holding reservations during the 15-minute proposal window reduces available quota for other concurrent workflows. Policy: reservations are held pessimistically. With a 100-call search budget and 15-minute windows, at most 6 concurrent proposals can be live before the search pool appears exhausted to new requests. This is acceptable for a local single-user server.

### 4. Warning Threshold (NFR-SA-4)

Warn when any pool reaches 80% utilisation (configurable via `quota_warn_threshold`, default 0.80). Warning appears in audit log and stderr.

### 5. Ambiguous Timeout Policy

After an ambiguous network timeout (HTTP 500/503 or no response) during a write:

- Assume quota **MAY** have been consumed (conservative)
- Do **not** release the reservation
- Mark the proposal as `PARTIAL` (ADR-C)
- Log the ambiguity in the audit trail
- On reconciliation (next restart or manual trigger), re-query API state before retrying

### 6. Midnight Reset

`QuotaLedger` does not auto-reset. The composition root re-creates it on each server startup. For long-running servers, a `ClockBasedQuotaReset` scheduler resets at midnight Pacific Time (injected via Clock port, testable with FakeClock).

---

## Consequences

- ✅ Over-budget workflows refused before first API call (FR-5.8, BR-5)
- ✅ Three independent pools correctly modelled
- ✅ SRS NFR-QU-1 stale figure flagged (C-1 resolution)
- ⚠️ 15-minute reservation hold reduces effective quota during proposal window
- ⚠️ `search.list` treated as scarce — FR-1 uses `videos.list` chains instead, requiring a known start point (upload playlist ID or channel ID)
