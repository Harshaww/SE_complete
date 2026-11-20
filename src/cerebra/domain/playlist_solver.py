"""Playlist constraint solver (FR-4.1 to FR-4.3).

Selects and orders videos so that:
  - total duration ≤ requested total (hard constraint)
  - each video duration ≤ max_video_duration (hard constraint, if given)
  - language matches (hard constraint, if given)
  - total duration ≥ fill_ratio × requested total (soft; report infeasible if unmet)
  - no duplicate IDs
  - fill ratio default 90% (TBD-8)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from cerebra.domain.entities import PlaylistItem, VideoMetadata

DEFAULT_FILL_RATIO = 0.90


@dataclass(frozen=True)
class SolverResult:
    items: list[PlaylistItem]
    total_seconds: int
    feasible: bool          # True if fill ratio met
    infeasible_reason: str  # non-empty when feasible=False


def solve_playlist(
    topic: str,
    total_duration_seconds: int,
    candidates: Sequence[VideoMetadata],
    max_video_duration_seconds: Optional[int] = None,
    language: Optional[str] = None,
    fill_ratio: float = DEFAULT_FILL_RATIO,
) -> SolverResult:
    """Greedy knapsack solver (FR-4.1 to FR-4.3).

    Candidates are assumed to be pre-ranked (highest relevance first).
    Returns a SolverResult with selected items in relevance order.
    """
    min_total = int(total_duration_seconds * fill_ratio)
    seen_ids: set[str] = set()
    selected: list[PlaylistItem] = []
    running_total = 0

    for video in candidates:
        # Hard constraints
        if video.video_id in seen_ids:
            continue
        if max_video_duration_seconds is not None:
            if video.duration_seconds > max_video_duration_seconds:
                continue
        if language:
            if video.language and video.language.lower() != language.lower():
                continue
        if running_total + video.duration_seconds > total_duration_seconds:
            continue

        # Accept video
        selected.append(
            PlaylistItem(
                video_id=video.video_id,
                title=video.title,
                channel_title=video.channel_title,
                duration_seconds=video.duration_seconds,
            )
        )
        seen_ids.add(video.video_id)
        running_total += video.duration_seconds

    feasible = running_total >= min_total
    infeasible_reason = ""
    if not feasible:
        pct = int(running_total / total_duration_seconds * 100) if total_duration_seconds else 0
        infeasible_reason = (
            f"Only {pct}% of the requested {total_duration_seconds // 60} minutes could be filled "
            f"(minimum required: {int(fill_ratio * 100)}%). "
            f"Try relaxing the max-video-duration or language constraints, or choose a broader topic."
        )

    return SolverResult(
        items=selected,
        total_seconds=running_total,
        feasible=feasible,
        infeasible_reason=infeasible_reason,
    )
