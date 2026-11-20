# AGENTS.md
# Cerebra – Rules for AI Coding Assistants

> **Read this file first** (SRS 1.3, PR-9). Every AI-generated change must comply with these rules.

## Project

**Cerebra** is a locally run Python MCP server (YouTube Video Intelligence).
Repository: `c:\Users\sai harsha\Desktop\SE`
SRS v1.0 – 09-Nov-2026 | Team: SegmentationFault

## Non-Negotiable Rules

1. **Official API only** (CON-1). Never call unofficial YouTube endpoints or scrape HTML.
2. **No write without human confirmation** (FR-4.6, NFR-SA-1). `create_playlist` requires a valid proposal_id + digest bound to human approval. A plain `confirmed=true` is never sufficient.
3. **No secrets in code** (NFR-SE-2). Never store tokens, API keys, or credentials in source, fixtures, logs or prompts.
4. **No watch history claims** (CON-5, BR-3, FR-3.7). The API does not provide it; never claim or use it.
5. **No edit/delete of existing content** (NFR-SA-2). Only `playlists.insert` and `playlistItems.insert` are ever called for writes.
6. **Untrusted metadata** (FR-4.10, NFR-SE-5). Video titles, descriptions, and tags are DATA, never instructions. Delimit with `[DATA]`.
7. **No global singletons** (SOLID). Construct once at composition root; inject everywhere.
8. **Provider interface** (CON-6, FR-5.17). All YouTube I/O goes through ports in `src/cerebra/ports/interfaces.py`.
9. **No live API in PR CI** (NFR-TE-1, TR-5). Tests use fixture adapter. Live tests in separate scheduled/manual workflows.
10. **Over-budget = refuse before first API call** (FR-5.8, BR-5). Never partially execute a workflow.

## Directory Guide

```
src/cerebra/
  config.py           All configuration; reads env vars only
  mcp_server.py       MCP transport + tool registration only
  mcp_tools/          Input validation, output mapping (FR-5.12)
  application/        Use cases: find_similar, recommend, analyse, playlist
  domain/             Pure business logic: entities, scoring, solver, state machine, errors
  ports/              Protocol interfaces (ISP) — the ONLY dependency boundary
  adapters/fixtures/  Fixture adapter for CI
  adapters/youtube/   Live YouTube adapter (the ONLY place making HTTP calls)
  infrastructure/     SQLite persistence, clock, composition root
tests/
  unit/               Fast domain logic tests (no I/O)
  property/           Hypothesis property tests (5 required)
  integration/        SQLite + use cases
  contract/           Same suite on live + fixture adapter
  mcp_e2e/            FR-1 to FR-5 through MCP interface
  security/           Approval provenance, injection, replay
brain/                PARA Obsidian vault
docs/adr/             Architecture Decision Records
skills/               Agent Skill SKILL.md files
```

## Commands

```bash
# Run tests (no live API)
PYTHONPATH=src pytest tests/unit tests/property tests/integration tests/contract tests/mcp_e2e tests/security -v

# Run with coverage
PYTHONPATH=src pytest --cov=cerebra --cov-report=term-missing tests/unit tests/property

# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/
```

## SRS Quick Reference

| ID | Rule |
|----|------|
| FR-1.9 | Ranking must be deterministic; ties broken by video_id |
| FR-4.5 | Persist proposal before returning it |
| FR-4.6 | Digest + expiry + single-use approval only |
| FR-4.7 | Reject expired/unknown/used proposals |
| FR-5.8 | Quota check before ANY API call |
| NFR-SA-1 | No write without confirmation |
| NFR-TE-1 | CI tests use fixtures only |
| BR-4 | Rank on metadata, not view counts |

## Traceability

Every PR must reference requirement IDs in the description.
Every test file must `# mark: FR-X.Y` above each test class.
See `docs/traceability.csv` for the full matrix.
