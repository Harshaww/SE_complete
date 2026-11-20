# ADR-A: Human Approval Provenance + MCP Trust Model

**Status:** Accepted  
**Date:** 2026-11-09  
**Deciders:** SegmentationFault team  
**SRS refs:** FR-4.6, FR-4.7, NFR-SA-1, NFR-SE-3, BR-2, CON-6, AS-2

---

## Context

Cerebra exposes a `create_playlist` MCP tool that performs a **write** to the user's YouTube account. Per FR-4.6 and NFR-SA-1, no write may happen without **human-originated** confirmation bound to the specific proposal.

MCP is a stateless JSON-RPC protocol. The MCP Python SDK version pinned is **`mcp>=1.9.0`** (per TBD-2). The spec version targeted is **2024-11-05** (the stable version available in mcp 1.9). That version:

- Uses an `initialize` / `initialized` handshake (not the stateless 2026-07-28 draft)
- Supports `tools/call`, `tools/list`, `resources/read`, `resources/list`
- Does **not** have server-initiated requests or Multi Round-Trip (MRTR) in stable form
- Transport: stdio (TBD-5)

> [!IMPORTANT]
> The MCP spec **does not authenticate clients**. Any process that can write to the server's stdin is a valid "client". Therefore: **the server must never trust arguments as proof of human action.**

---

## Decision

### 1. Proposal Digest Binding (FR-4.6)

Every `propose_playlist` response includes:

```json
{
  "proposal_id": "<uuid4>",
  "confirmation_digest": "<sha256(proposal_id + topic + video_ids_sorted + expiry_ts + account_id)>",
  "expires_at": "<ISO-8601>",
  "videos": [...],
  "⚠️ WARNING": "Review the video list above. Pass proposal_id + confirmation_digest to create_playlist."
}
```

`create_playlist` requires **both** `proposal_id` and `confirmation_digest`. The server:

1. Looks up the proposal by `proposal_id` — must exist and be in `PROPOSED` state
2. Recomputes the digest from stored proposal fields — must match `confirmation_digest` exactly
3. Checks `expires_at` — must not be expired (default 15 minutes, `proposal_expiry_seconds` in config)
4. Marks the proposal `CONFIRMED` atomically in SQLite before any API call
5. Marks it single-use: a second call with the same `proposal_id` after `CONFIRMED` → raises `PROPOSAL_ALREADY_USED`

A plain `confirmed=true` argument is **never** accepted. The digest is the cryptographic binding: it proves the caller saw the proposal content (video list, topic) because the digest covers those fields.

### 2. Account Identity Binding

In Phase 2–3 (fixture adapter), account identity is a stub `"fixture_user"`. In Phase 4+, the OAuth token's `sub` claim (Google account ID) is embedded in the digest. A replay from a different OAuth account fails digest verification.

### 3. Out-of-Band Approval Channel

For stdio transport, **all human-readable prompts go to stderr**, never stdout (which carries MCP JSON). An optional approval CLI is provided:

```
python -m cerebra.cli approve <proposal_id>
```

This reads the proposal from SQLite, displays it to the terminal (stderr/tty), and writes an `approval_token` to SQLite that `create_playlist` checks. This channel is used when the AI client does not support interactive confirmation.

### 4. MCP Client Trust Model

| Client type | Trust level | Notes |
|-------------|------------|-------|
| Claude Desktop (stdio) | Untrusted relay | User types confirmation_digest from proposal output |
| Automated agent loop | Untrusted | Digest binding prevents auto-approval |
| `cerebra.cli approve` | Trusted (local) | Runs in user's terminal, reads tty |

The server **fails closed** when a client calls `create_playlist` without a valid digest: `APPROVAL_REJECTED` error, no write occurs.

### 5. Replay and Expiry Protection

| Attack | Mitigation |
|--------|-----------|
| Replay same proposal | Single-use: state machine → CONFIRMED → no further transitions to CREATED from same call |
| Expired proposal | `expires_at` checked server-side; `PROPOSAL_EXPIRED` error |
| Wrong digest | Constant-time compare via `hmac.compare_digest` |
| Injected metadata in proposal | Video titles/descriptions treated as `[DATA]`, never evaluated |
| Wrong account | Digest includes account `sub` (Phase 4+) |

### 6. Elicitation Note

MCP 2026-07-28 draft introduces elicitation (server asks client for input). This is **not** relied upon for security: a client can auto-answer elicitation prompts. The digest approach is used instead, which is verifiable server-side regardless of how the client obtained it.

---

## Consequences

- ✅ No write path exists without digest + proposal_id + non-expired + non-used proposal
- ✅ Agent-generated `confirmed=true` is ignored
- ✅ Works with any MCP client including fully automated ones (they just can't approve writes)
- ⚠️ User must copy the `confirmation_digest` from the proposal output — slight UX friction
- ⚠️ 15-minute expiry window means slow users may need to re-propose

---

## Rejected Alternatives

- **`confirmed=true` flag** — rejected: trivially bypassed by any agent (NFR-SA-1)
- **MCP elicitation for approval** — rejected: clients may auto-answer (not human-proof)
- **OAuth callback approval** — deferred to Phase 5 (TBD-11)
