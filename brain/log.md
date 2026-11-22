# Development Log

## 2026-11-22

### brain-ingest (AI-assisted drafts, review pending)
- Added 10 research notes and 1 ai-session note (see [[ai-session-2026-11-22-brain-drafts]]).
- Added frontmatter to the 3 existing notes.
- Created the 3 notes cited by skills (SK-6.1): cerebra-knowledge-system, cerebra-skill-design, cerebra-dev-workflow.

## 2026-11-20

### Unit Tests: 134 passed ✅

All unit tests passing after:
- Fixing `test_no_api_call_on_rejection` (used `"not_valid!!"` instead of `"not-a-video"` which is a valid 11-char ID)
- Adding path-traversal detection to `validate_reference` for `test_path_traversal_in_reference_rejected`
- Creating `mcp` stub module at `src/mcp/__init__.py` to handle offline pip install failures
- Creating missing `__init__.py` files for infrastructure sub-packages

### Packages Installed
- scikit-learn ✅, numpy ✅, pydantic ✅, pytest ✅, pytest-asyncio ✅, pytest-cov ✅, hypothesis ✅
- mcp ❌ (network failure) → workaround: local stub at `src/mcp/`
- pytest-mock ❌ (network failure) → workaround: rewrote test without mocker fixture
- ruff ❌ (network failure) → will retry

### ADRs Created
- ADR-A: MCP trust model, approval provenance ✅
- ADR-B: Quota model, 3-pool system, stale NFR-QU-1 flag ✅
- ADR-C: Write idempotency, before-write state persist ✅
- ADR-D: OAuth scopes (youtube.readonly + youtube) ✅
- ADR-E: Storage (SQLite), transport (stdio), TBD-2..12 ✅

## 2026-11-09 (SRS date)

### Project Kickoff

SRS v1.0 received. Team: SegmentationFault.
Key decisions:
- Python 3.12 (SRS says ≥3.11 ✓)
- SQLite for all persistence (TBD-3)
- stdio transport (TBD-5)
- Weights: w1=0.60, w2=0.15, w3=0.10, w4=0.10, w5=0.05 (A-1)
- search.list treated as scarce; prefer videos.list (C-1)
