# Changelog

All notable changes to Cerebra. Format: Keep a Changelog; versions follow SemVer. Requirement IDs
refer to SRS v1.0 (PR-6).

## [Unreleased]

### Added
- Live YouTube adapter, OAuth manager, human-approval CLI, recovery command (Phases 3-5; FR-4.6, FR-4.13, FR-5.1 to FR-5.5, NFR-SA-1).
- `cerebra-cli clear-cache` and cache retention cap (NFR-PV-2).
- Headless auth via `CEREBRA_REFRESH_TOKEN` (never persisted) and the manual live-API test suites
  `live_readonly` / `live_write` with `scripts/redact_results.py` (TR-5, NFR-SE-2).
- Traceability checker `scripts/traceability.py`, run in CI (PR-4).

### Changed
- Proposal state machine now allows only PARTIAL -> CREATED from PARTIAL, as in SRS Appendix B.3.
- Package license metadata is BSD-3-Clause, matching `LICENSE`.

### Fixed
- Removed the `src/mcp` stub that shadowed the real `mcp` package.
- `ruff check` and `ruff format --check` pass on `src/` and `tests/` (NFR-MA-2).
- `validate_brain.py` passes in a clean clone (empty PARA directories are tracked).
