---
title: API errors and retry policy
type: research-note
status: draft
source: https://developers.google.com/youtube/v3/docs/errors
accessed: 2026-11-22
author: unassigned
drafted-with: ai, see [[ai-session-2026-11-22-brain-drafts]]
requirements: [FR-5.10, FR-5.15, NFR-RE-1, NFR-RE-2, FR-5.4]
---

# API errors and retry policy

| Situation | Cerebra behaviour |
|-----------|-------------------|
| quotaExceeded | Never retry; return QUOTA_EXHAUSTED and say when the quota resets (midnight Pacific). FR-5.10 |
| Rate limiting, 5xx backend errors | Retry at most 3 times with exponential back-off. NFR-RE-2 |
| Invalid or expired credentials | Return AUTH_EXPIRED and guide re-authorisation. FR-5.4 |
| youtubeSignupRequired | NO_YOUTUBE_CHANNEL, create nothing. FR-4.12 |
| Unknown or private video | Empty result, mapped to VIDEO_NOT_FOUND_OR_PRIVATE. FR-1.2 |

Every error leaves the server as the same structure: code, message, retryable flag, suggested next
step (FR-5.15, NFR-US-1). Retrying a permanent error only burns quota ([[quota-notes]]).
Related: [[playlist-writes]], [[oauth-scopes]].
