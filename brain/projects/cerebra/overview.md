# Cerebra Project Overview

**Project:** Cerebra – YouTube Video Intelligence MCP Server  
**Course:** Software Engineering Lab  
**Team:** SegmentationFault  
**Roll:** BT2024148 (Sai Harsha)  
**SRS Version:** 1.0, 2026-11-09

---

## Goal

Build a locally-run Python MCP server that:
1. Finds similar YouTube videos/channels (FR-1, FR-2)
2. Recommends videos from user's library (FR-3)
3. Analyses engagement patterns (FR-3)
4. Proposes and creates YouTube playlists with human approval (FR-4)

---

## Architecture Decision Summary

| ADR | Decision |
|-----|---------|
| ADR-A | Approval = digest + proposal_id + expiry + single-use |
| ADR-B | 3-pool quota; prefer videos.list over search.list (C-1) |
| ADR-C | Before-write state persist; read-before-retry |
| ADR-D | youtube.readonly (read) + youtube (write, incremental) |
| ADR-E | SQLite + stdio + all TBDs resolved |

---

## Scoring Weights (A-1)

| Signal | Weight |
|--------|--------|
| TF-IDF cosine similarity | 0.60 |
| Category match | 0.15 |
| Channel affinity | 0.10 |
| Language match | 0.10 |
| Duration proximity | 0.05 |

---

## Open SRS Conflicts

| ID | Conflict | Resolution |
|----|---------|-----------|
| C-1 | NFR-QU-1 assumes search.list; limited to 100/day | Flag in ADR-B; prefer videos.list |
| A-6 | No watch history API | Disclose: "based on likes, subscriptions, playlists" |

---

## Test Status

- Unit: 134 passed ✅
- Property: 6 Hypothesis tests ✅ (5 required + 1 bonus)
- Integration: See test run
- Security: Approval provenance, replay, expiry ✅
