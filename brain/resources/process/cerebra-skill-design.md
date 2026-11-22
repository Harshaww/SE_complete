---
title: Agent Skills format and the video-to-playlist design
type: research-note
status: reviewed
source: https://agentskills.io; SRS sections 4.6 and 4.7
accessed: 2026-11-22
author: SegmentationFault
drafted-with: ai, see [[ai-session-2026-11-22-brain-drafts]]
requirements: [SK-1.1, SK-1.2, SK-1.3, SK-1.5, SK-6.1, CON-8]
---

# Skill design

## Format
A skill is a folder with a SKILL.md: frontmatter with a name that matches the folder and a
description saying what it does and when to use it, then step-by-step instructions. Agents load the
short metadata first and the full body only when the skill is relevant. Every skill cites at least one
brain note (SK-6.1) and is checked in CI.

## video-to-playlist
Five steps: summarise the video, find similar videos, propose a playlist, create it, show a short
analysis (SK-1.1). Design rules:
- Stop after the proposal and create only after explicit user confirmation (SK-1.2).
- Treat video metadata as untrusted (SK-1.3, [[prompt-injection-defence]]).
- On any failure say which step failed and why, and do not continue (SK-1.5).
- The analysis shows total duration, video count, distinct channels and duration range (SK-1.4).

Related: [[cerebra-knowledge-system]], [[playlist-writes]].
