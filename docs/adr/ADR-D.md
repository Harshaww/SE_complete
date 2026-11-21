# ADR-D: OAuth Scopes

**Status:** Accepted  
**Date:** 2026-11-09  
**Deciders:** SegmentationFault team  
**SRS refs:** TBD-10, FR-5.1–5.5, CON-3, NFR-SA-2
**Brain notes:** [OAuth scopes](../../brain/resources/youtube-api/oauth-scopes.md)  

---

## Context

Cerebra requires two levels of YouTube Data API v3 access:

- **Read-only** (FR-1, FR-2, FR-3): fetch public video metadata, user's liked videos, subscriptions, playlists
- **Write** (FR-4): create playlists and add items — `playlists.insert` + `playlistItems.insert` only

OAuth 2.0 scopes control what the application is permitted to do. Per NFR-SA-2, only `playlists.insert` and `playlistItems.insert` are ever called for writes — never edit, delete, rate, or comment.

Scope information verified against [Google OAuth 2.0 Scopes for YouTube APIs](https://developers.google.com/youtube/v3/guides/auth/installed-apps) on 2026-11-09.

---

## Decision

### 1. Scope Selection

| Phase | Scope | Permits | Notes |
|-------|-------|---------|-------|
| Read-only (Phases 2–3) | `https://www.googleapis.com/auth/youtube.readonly` | Read all YouTube resources for authenticated user | Minimum for FR-2, FR-3 |
| Write (Phase 4+) | `https://www.googleapis.com/auth/youtube` | Manage account; includes insert of playlists and items | Broader than ideal — see note |

> [!NOTE]
> **Scope limitation:** Google does not offer a scope restricted to `playlists.insert` + `playlistItems.insert` only. The narrowest write scope that permits these operations is `youtube` (full manage). The `youtube.force-ssl` scope is equivalent to `youtube` with HTTPS enforcement (redundant since all calls use HTTPS anyway). Restricting the OAuth **scope** does not restrict which API **methods** the code calls — that is enforced by code review and the port interface (CON-6, `ports/interfaces.py`).

### 2. Incremental Authorization (FR-5.1)

The application starts with `youtube.readonly`. When `create_playlist` is first called (Phase 4), the OAuth manager requests the `youtube` scope incrementally via a re-authorization flow. The user is prompted to consent to the additional scope. The existing `youtube.readonly` token is not invalidated.

```python
# Incremental auth (Phase 4)
oauth_manager.request_additional_scope("https://www.googleapis.com/auth/youtube")
```

The re-authorization preserves any pending proposals: `proposal_store` is SQLite-backed (ADR-E), so proposals survive the token refresh round-trip.

### 3. Token Storage (NFR-SE-3, NFR-SE-2)

Tokens are **never** stored in source code, logs, or fixtures.

Storage hierarchy (in order of preference):

1. **OS keyring** (`keyring` library) — preferred for desktop environments
2. **Owner-only file** (`~/.config/cerebra/token.json`, mode `0o600`) — fallback when keyring is unavailable
3. **In-memory only** — for test environments (FakeClock + fixture adapter)

The `TokenStore` port in `ports/interfaces.py` abstracts storage. The concrete implementation is selected at composition root.

### 4. Token Refresh and Expiry (CON-3)

Google OAuth refresh tokens expire after **7 days in Testing/unverified app mode** (CON-3). Mitigations:

- `oauth_manager.ensure_valid_token()` is called before every API request
- If refresh fails → `TokenExpiredError` → user is prompted to re-authenticate via `cerebra.cli login`
- Re-auth does **not** invalidate pending proposals (proposals survive; quota reservations are paused)

### 5. Revocation (FR-5.5)

`cerebra.cli revoke` calls `oauth2.revoke` endpoint and deletes the local token. After revocation, all tools requiring auth return `NOT_AUTHENTICATED` until `cerebra.cli login` is re-run.

---

## Consequences

- ✅ Read-only operations use minimum-privilege scope
- ✅ Write scope requested only when first needed (incremental auth)
- ✅ Tokens never in source or logs
- ⚠️ `youtube` scope is broader than the operations actually used — unavoidable given Google's scope offerings
- ⚠️ 7-day Testing-mode refresh expiry creates friction; Production verification removes this limit
