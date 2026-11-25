# ADR-E: Persistence, Transport, and TBD Resolutions

**Status:** Accepted  
**Date:** 2026-11-09  
**Deciders:** SegmentationFault team  
**SRS refs:** TBD-2 through TBD-12, NFR-TE-1, NFR-PF-1
**Brain notes:** [Cerebra overview](../../brain/projects/cerebra/overview.md)  

---

## Context

The SRS listed several open TBDs to be resolved during implementation. This ADR records all decisions for TBD-2 through TBD-12.

---

## Decisions

### TBD-2: Dependency Versions

| Package | Pinned version | Rationale |
|---------|---------------|-----------|
| Python | ≥3.11 (using 3.12.10) | SRS §2.4 says ≥3.11; 3.12 is current stable |
| `mcp` | `>=1.9.0` | Latest stable MCP Python SDK; spec version 2024-11-05 |
| `scikit-learn` | `>=1.3` | TF-IDF via `TfidfVectorizer`; 1.3+ required for `set_output` API |
| `numpy` | `>=1.24` | Required by scikit-learn |
| `pydantic` | `>=2.0` | Used for config validation |
| `pytest` | `>=8.0` | Required for `--import-mode=importlib` |
| `hypothesis` | `>=6.0` | Property testing (Lab Part A) |
| `pytest-asyncio` | `>=0.23` | Async test support |
| `pytest-cov` | `>=4.0` | Coverage reports |
| `httpx` | `>=0.27` | HTTP client for live YouTube adapter |
| `google-api-python-client` | `>=2.100` | YouTube Data API v3 client (Phase 3+) |
| `google-auth-oauthlib` | `>=1.2` | OAuth 2.0 flow |
| `keyring` | `>=24.0` | Secure token storage |
| `ruff` | `>=0.4` | Lint + format |

### TBD-3: Storage Backend

**Decision: SQLite** (via Python stdlib `sqlite3`)

Rationale:
- Local-only server; no distributed state
- Zero additional infrastructure
- ACID transactions for quota + proposal atomicity
- File-based; trivially backed up
- Adequate for single-user, <1000 proposals/day load

Schema:
- `proposals` table: `proposal_id`, `state`, `topic`, `video_ids_json`, `digest`, `created_at`, `expires_at`, `playlist_id`, `reservation_id`
- `proposal_items` table: `proposal_id`, `video_id`, `item_index`, `item_state`
- `cache_entries` table: `cache_key`, `value_pickle`, `expires_at`, `created_at`
- `audit_log` table: `id`, `event_type`, `proposal_id`, `actor`, `detail_json`, `created_at`, `ambiguous`
- `quota_snapshots` table: `pool`, `consumed`, `snapshot_at`

### TBD-5: Transport

**Decision: stdio only** (Phases 2–4)

Rationale: MCP stdio transport is the standard for local desktop AI assistants (Claude Desktop, etc.). HTTP/SSE transport deferred to Phase 5 (TBD-5 extended).

### TBD-6: Cache Retention Policy

- Default TTL: 300 seconds (5 minutes) for video/channel metadata
- Max cache size: 1,000 entries (LRU eviction)
- Cache is **per-account**: keys include account hash to prevent cross-account data leakage
- Cache is **not** shared across OS users
- Manual clear: `cerebra-cli clear-cache`

### TBD-7: Duration Bands

| Band | Range | Label |
|------|-------|-------|
| short | < 4 minutes (< 240 s) | "short" |
| medium | 4–20 minutes (240–1200 s) | "medium" |
| long | > 20 minutes (> 1200 s) | "long" |

### TBD-8: Ranking Weights

| Signal | Weight | Symbol |
|--------|--------|--------|
| TF-IDF cosine similarity (title + description + tags) | 0.60 | w1 |
| Category match | 0.15 | w2 |
| Channel affinity | 0.10 | w3 |
| Language match | 0.10 | w4 |
| Duration proximity | 0.05 | w5 |

Ties broken by `video_id` lexicographic order (FR-1.9, determinism).

### TBD-9: Log Redaction

- Video IDs, channel IDs, proposal IDs: logged as-is (not PII)
- OAuth tokens: **never** logged
- User account ID (`sub` claim): logged as `sha256(sub)[:8]` prefix only
- Video titles, descriptions: logged with `[DATA]` prefix; truncated to 100 chars
- IP addresses: not applicable (local server, no network binding)

### TBD-10: OAuth Scopes

See ADR-D.

### TBD-11: Production OAuth Verification

Deferred to Phase 5. Currently app is in Testing mode (7-day refresh limit per CON-3).

### TBD-12: Concurrency Model

- Server is single-process, single-instance
- Async I/O via `asyncio` (MCP SDK requirement)
- SQLite writes use a module-level `threading.Lock` (one writer at a time)
- `QuotaLedger` uses `threading.Lock` for atomic reserve/release
- No global mutable singletons: all state injected via Container

---

## Persistence Schema (SQLite DDL)

```sql
CREATE TABLE proposals (
    proposal_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    topic TEXT NOT NULL,
    video_ids_json TEXT NOT NULL,
    digest TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    playlist_id TEXT,
    reservation_id TEXT,
    account_id TEXT
);

CREATE TABLE proposal_items (
    proposal_id TEXT NOT NULL,
    video_id TEXT NOT NULL,
    item_index INTEGER NOT NULL,
    item_state TEXT NOT NULL DEFAULT 'PENDING',
    PRIMARY KEY (proposal_id, item_index),
    FOREIGN KEY (proposal_id) REFERENCES proposals(proposal_id)
);

CREATE TABLE cache_entries (
    cache_key TEXT PRIMARY KEY,
    value_pickle BLOB NOT NULL,
    expires_at REAL NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    proposal_id TEXT,
    actor TEXT,
    detail_json TEXT,
    created_at REAL NOT NULL,
    ambiguous INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE quota_snapshots (
    pool TEXT NOT NULL,
    consumed INTEGER NOT NULL DEFAULT 0,
    snapshot_at REAL NOT NULL,
    PRIMARY KEY (pool)
);
```

---

## Consequences

- ✅ All TBDs resolved; no open unknowns in Phase 2
- ✅ SQLite gives ACID guarantees without external dependencies
- ✅ stdio transport matches Claude Desktop / standard MCP deployment
- ⚠️ SQLite `threading.Lock` is a global lock; acceptable for single-user local server
- ⚠️ `mcp>=1.9.0` requires pip install at runtime; stub provided for offline development
