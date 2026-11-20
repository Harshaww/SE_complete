# ADR-C: Write Idempotency + Recovery

**Status:** Accepted  
**Date:** 2026-11-09  
**Deciders:** SegmentationFault team  
**SRS refs:** FR-4.6, FR-4.8, NFR-SA-1, NFR-SA-2, SRS Appendix B.3

---

## Context

`create_playlist` performs two types of writes to the YouTube API:

1. `playlists.insert` — creates the playlist shell (one call)
2. `playlistItems.insert` — adds each video (N calls, one per video)

Network failures, process crashes, or API errors between steps leave the system in a **partial state**: a playlist may exist on YouTube with zero or some videos, while the local proposal record is in an ambiguous state.

Per NFR-SA-2, only `playlists.insert` and `playlistItems.insert` are ever called. Per ADR-A, writes require confirmed approval. Recovery must **never blind-retry** a write (risk of duplicate playlists or items).

---

## Decision

### 1. State Machine (SRS Appendix B.3)

```
PROPOSED ──(confirmed + digest ok)──→ CONFIRMED
CONFIRMED ──(first write attempted)──→ PARTIAL (persist playlist_id)
PARTIAL ──(all items inserted)──→ CREATED
PARTIAL ──(unrecoverable error)──→ FAILED

PROPOSED ──(expired)──→ EXPIRED
PROPOSED ──(cancelled)──→ CANCELLED
CONFIRMED ──(expired before write starts)──→ EXPIRED
```

Terminal states: `CREATED`, `EXPIRED`, `CANCELLED`, `FAILED`

### 2. Before-Write State Persist

The sequence for every write operation:

```
1. Transition proposal state to PARTIAL (SQLite, transactional)
2. Store playlist_id = None (not yet created)
3. Call playlists.insert
4. On success: store playlist_id in proposal record (SQLite, transactional)
5. For each video:
   a. Mark item as PENDING in proposal.items (SQLite)
   b. Call playlistItems.insert(playlist_id, video_id)
   c. On success: mark item as INSERTED (SQLite, transactional)
   d. On failure: mark item as FAILED; continue with remaining items
6. After all items: if all INSERTED → transition to CREATED; else → stay PARTIAL
```

> [!IMPORTANT]
> **State is persisted BEFORE each write.** On crash recovery, the server reads PARTIAL proposals on startup and can determine exactly which items succeeded vs. failed.

### 3. Recovery Protocol

On server startup, for each proposal in `PARTIAL` state:

1. If `playlist_id` is None → `playlists.insert` may or may not have succeeded
   - **Do not blind-retry.** Query `playlists.list` for the account to find playlists matching the title + recent creation time
   - If found → record `playlist_id`, continue to item recovery
   - If not found → safe to retry `playlists.insert` (playlist creation is idempotent by title + description in practice, though not guaranteed by API)
2. If `playlist_id` is known → skip `playlists.insert` (already created)
3. For each item marked `PENDING` or `FAILED`:
   - Query `playlistItems.list(playlist_id)` to check if already inserted
   - If already present → mark INSERTED (no retry needed)
   - If absent → retry `playlistItems.insert` once

### 4. Never Blind-Retry

> [!CAUTION]
> Never call `playlists.insert` or `playlistItems.insert` without first checking remote state via a read (`playlists.list` / `playlistItems.list`). Blind retries risk:
> - Duplicate playlists on YouTube
> - Duplicate items in a playlist

### 5. Idempotency Keys

For Phase 4+: include a stable `idempotency_key` (SHA-256 of `proposal_id + item_index`) in `playlistItems.insert` requests. The YouTube API does not natively support idempotency keys, so the read-before-write check (step 3 above) is the primary guard.

### 6. Ambiguous Failure Handling

If `playlists.insert` or `playlistItems.insert` returns HTTP 5xx / timeout:

- Quota assumed consumed (ADR-B §5)
- State remains `PARTIAL`
- Error logged to `AuditLog` with `ambiguous=True`
- Next startup or manual `cerebra.cli recover <proposal_id>` triggers reconciliation

---

## Consequences

- ✅ No data loss: each write is preceded by a persistent state record
- ✅ No duplicate playlists: recovery reads remote state before retrying
- ✅ Partial failures recoverable: per-item tracking
- ⚠️ Recovery requires extra `playlists.list` / `playlistItems.list` read calls (quota cost)
- ⚠️ Phase 2–3 uses fixture adapter; this protocol is exercised in Phase 4 integration tests
