# Cerebra Brain – PARA Vault Index

> Personal knowledge management vault for the Cerebra project.

## PARA Structure

| Folder | Purpose |
|--------|---------|
| `projects/cerebra/` | Active project notes, decisions, open questions |
| `areas/` | Ongoing responsibilities (API monitoring, quota) |
| `resources/youtube-api/` | YouTube API v3 reference notes |
| `resources/mcp/` | MCP protocol notes |
| `archive/` | Completed items |

---

## Quick Links

- [Project Overview](projects/cerebra/overview.md)
- [YouTube API Quota Notes](resources/youtube-api/quota-notes.md)
- [OAuth Scopes Reference](resources/youtube-api/oauth-scopes.md)
- [Development Log](log.md)

---

## SRS Status

| Phase | Status | Key deliverable |
|-------|--------|----------------|
| Phase 0 – Recon | ✅ Done | ADRs drafted, TBDs resolved |
| Phase 1 – Design | ✅ Done | ADR-A through ADR-E |
| Phase 2 – Foundation | ✅ Done | Domain + ports + fixture adapter + unit tests |
| Phase 3 – Read-only | 🚧 In progress | Live YouTube adapter |
| Phase 4 – Safe write | 🔲 Planned | OAuth + create_playlist |
| Phase 5 – Productization | 🔲 Planned | Error handling, perf, docs |

---

## Open Questions

- TBD-11: Production OAuth app verification (university project — may remain in Testing mode)
- TBD-4: Re-verify quota costs at implementation time (cite official page)
