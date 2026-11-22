---
title: Cerebra development workflow, local-check and CI gate
type: research-note
status: reviewed
source: SRS sections 4.7 and 6.1; AGENTS.md; .github/workflows/ci.yml
accessed: 2026-11-22
author: SegmentationFault
drafted-with: ai, see [[ai-session-2026-11-22-brain-drafts]]
requirements: [SK-2.1, SK-2.2, PR-4, PR-5, PR-6, CON-7, TR-5]
---

# Development workflow

## Local gate (same as CI)
ruff check, ruff format --check, mypy, then the pytest suite with coverage. Dependencies are installed
from requirements.lock so local and CI environments match.

## local-check skill
Build, run the tests, start the local server, call one read-only endpoint and report each step
(SK-2.1). It uses fixtures only, so it cannot touch a YouTube account (SK-2.2).

## Traceability
Commit messages and test markers carry requirement IDs; scripts/traceability.py checks that every
requirement maps to evidence (PR-4). CI also validates skills and this vault (PR-5).

## Process rules
Changes go through pull requests with at least one human review (CON-7, PR-6). Live API tests are
separate from PR CI and run only by hand or on a schedule (TR-5); see the live smoke runbook in
docs/testing. Live smoke run completed 2026-11-22: 7/7 read-only tests passed, FR-1 latency
1.82 s (NFR-PF-3 met). Related: [[cerebra-knowledge-system]], [[cerebra-skill-design]].
