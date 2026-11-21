# ADR-F: Phase 3-5 Implementation Notes (deviations and clarifications)

**Status:** Accepted | **Date:** 2026-11-21 | **Refs:** ADR-A, ADR-B, ADR-C, ADR-D
**Brain notes:** [Cerebra overview](../../brain/projects/cerebra/overview.md), [Quota notes](../../brain/resources/youtube-api/quota-notes.md), [OAuth scopes](../../brain/resources/youtube-api/oauth-scopes.md)  

These record where the implementation refines or departs from the earlier ADRs.

1. **Human approval is enforced, not just a digest (ADR-A).** The digest appears in the
   `propose_playlist` output, so an MCP client can always echo it back; it proves nothing about a
   human. Live mode therefore also requires an approval row written by
   `cerebra-cli approve`, which needs an interactive TTY and makes the user re-type 8 digest
   characters. The approval is single-use and bound to digest and account. Fixture mode (CI) keeps
   digest-only behaviour so the existing suites are unchanged.
2. **Account identity = YouTube channel ID (ADR-A §2).** `youtube.readonly`/`youtube` scopes give no
   OpenID `sub`; `channels.list(mine=true)` (1 unit) is used instead and folded into the digest.
3. **Quota in live mode (ADR-B).** The adapter reserves/consumes per call; use cases only make the
   up-front can-afford decision (`AdapterMeteredQuota`). Consequence: no 15-minute worst-case hold
   during the proposal window in live mode; the write is instead re-checked (`50 + 50n`) before
   anything is persisted or written. The ledger is persisted per Pacific day (`PersistentQuotaLedger`).
4. **Recovery is explicit (ADR-C §3).** Startup lists PARTIAL proposals on stderr but performs no
   writes; `cerebra-cli recover` does the read-before-write reconciliation. The playlist is
   located by the proposal id embedded in its description (more precise than title + time).
   Item positions are "number already inserted" so a failed item never leaves a gap. The
   idempotency key of ADR-C §5 is not sent because the API ignores it; read-before-retry is the guard.
5. **Playlist title/description are plain text.** The `[DATA]` marker is a model-facing delimiter and
   is no longer written into the user's YouTube playlist; `<`/`>` are stripped and lengths clamped
   to YouTube's limits.
6. **Token file location (ADR-D §3).** `~/.config/cerebra/token.json` (or `$XDG_CONFIG_HOME`),
   directory `0700`, file `0600`, atomic replace. Keyring failures fall back to the file.
7. **`ensure_write_access()` added to `PlaylistWriter`** so the scope upgrade happens before any state
   change; the fixture writer implements it as a no-op.
8. **Coverage scope.** `adapters/youtube/` is no longer omitted from coverage; it is tested through
   an in-memory double of the googleapiclient resource.
9. **MCP SDK pin.** `mcp_server.py` uses the 1.x low-level `Server` decorators (`list_tools`,
   `call_tool`, ...). mcp 2.x removes them, so `pyproject.toml` pins `mcp>=1.9.0,<2`. Verified end to
   end over real stdio with mcp 1.30.0 (initialize + tools/list, stdout carries JSON only).
10. **State machine matches SRS Appendix B.3.** `PARTIAL` may only go to `CREATED`. The earlier
    `PARTIAL -> FAILED` edge was never used by production code and is removed; an unrecoverable
    partial proposal stays `PARTIAL` and is reported by `cerebra-cli pending`.
11. **NFR-QU-1 is met by actual cost, not by reservation.** A typical FR-1 request costs about 104
    units and a typical proposal about 102 (tests/integration/test_privacy_and_budgets.py). The
    quota reservation made before the first call is deliberately a worst-case upper bound
    (FR-4.11, ADR-B), so a reserved figure above 250/400 is expected and is not a violation.
12. **FR-5.4 scope.** An expired or revoked refresh token is detected before the single-use approval
    is burned and before any state change, so the proposal and its approval stay usable after
    re-authorisation (tested). Residual case: if Google rejects an already-issued access token
    with 401 in the middle of `playlists.insert`, nothing was written but the proposal is marked
    `FAILED` and the user must propose and approve again.
13. **Cache retention and clear command (NFR-PV-2).** `CEREBRA_CACHE_RETAIN_DAYS` now caps every
    cache TTL, and `cerebra-cli clear-cache` deletes all cached YouTube data.
14. **Headless runs.** `CEREBRA_REFRESH_TOKEN` (+ `CEREBRA_REFRESH_TOKEN_SCOPES`) supplies
    credentials for scheduled live-API CI. It is held in memory only, never written to the token
    store, and never opens a browser.
