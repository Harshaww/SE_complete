---
title: videos.list metadata fields Cerebra uses
type: research-note
status: reviewed
source: https://developers.google.com/youtube/v3/docs/videos/list
accessed: 2026-11-22
author: SegmentationFault
drafted-with: ai, see [[ai-session-2026-11-22-brain-drafts]]
requirements: [FR-1.2, FR-1.3, FR-3.5, AS-3, BR-4]
---

# videos.list metadata

## Parts we request
- snippet: title, description, tags (optional), categoryId, channelId, default language fields.
- contentDetails: duration as an ISO 8601 string, see [[iso8601-duration]].
- statistics exists but is not used for ranking (BR-4).

## Behaviour that shapes the design
- One call can look up many video IDs (up to 50), and costs 1 unit per call (see [[quota-notes]]),
  which is why Cerebra prefers chains of videos.list over search.list.
- An ID that is deleted, private or unknown is simply absent from the response items; it is not an
  HTTP error. Cerebra turns the empty result into VIDEO_NOT_FOUND_OR_PRIVATE (FR-1.2).
- Tags and language fields are optional, so every consumer must cope with missing values (AS-3,
  FR-1.8; see [[tfidf-cosine]]).
