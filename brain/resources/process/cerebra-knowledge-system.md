---
title: The Cerebra second brain: PARA vault and brain skills
type: research-note
status: reviewed
source: https://obsidian.md; SRS section 4.7; PARA organisation method
accessed: 2026-11-22
author: SegmentationFault
drafted-with: ai, see [[ai-session-2026-11-22-brain-drafts]]
requirements: [SK-3.1, SK-4.1, SK-5.1, PR-9, PR-10, BR-6]
---

# Second brain

## Structure
The brain/ folder is an Obsidian vault: plain Markdown files. PARA sorts notes by actionability:
projects, areas, resources, archive, plus an inbox for unsorted material. index.md is the entry
point and log.md is an append-only record of skill runs.

## Notes
- Each note has frontmatter (title, type, source, requirements) and `[[wikilinks]]` that resolve by file
  name. Notes cite requirement IDs, and ADRs cite notes (NFR-MA-3).
- Distilled means written in our own words with the source recorded; no pasted copyrighted text
  (SK-3.2).
- Every member authors notes, and AI-assisted drafts are recorded as ai-session notes (PR-9, PR-11).

## Skills
brain-ingest puts new material in the inbox and logs it; brain-refine files notes into PARA, merges
duplicates, fixes links and updates the index; brain-query answers from notes and cites them, and
changes nothing except the log (SK-3 to SK-5). Related: [[cerebra-skill-design]],
[[cerebra-dev-workflow]], [[overview]].
