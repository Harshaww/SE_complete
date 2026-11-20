"""Application use case: recommend_videos (FR-2)."""
from __future__ import annotations

from typing import Optional

from cerebra.config import Config
from cerebra.domain.entities import SimilarVideo, VideoMetadata
from cerebra.domain.errors import auth_required, quota_budget_exceeded
from cerebra.domain.quota import QuotaLedger
from cerebra.domain.scoring import rank_videos
from cerebra.ports.interfaces import CacheStore, PublicVideoReader, UserLibraryReader


LIKED_VIDEO_CAP_NOTE = (
    "Based on up to 1,000 most recently liked videos accessible via the YouTube API; "
    "complete like history is not available from the API."
)
NOT_WATCH_HISTORY_NOTE = (
    "Results are based on liked videos, subscriptions and playlists — not watch history. "
    "Watch history is not available through the YouTube API (CON-5, BR-3)."
)


class RecommendVideosUseCase:
    """FR-2: Video Recommendations from liked videos, subscriptions and playlists.

    FR-2.2: Profile from liked videos, subs and playlists ONLY.
    FR-2.6: Empty result (not error) for empty profile.
    CON-5/BR-3: No watch history claims.
    """

    def __init__(
        self,
        video_reader: PublicVideoReader,
        user_library: UserLibraryReader,
        quota: QuotaLedger,
        cache: CacheStore,
        config: Config,
        is_authenticated: bool = False,
    ) -> None:
        self._video = video_reader
        self._library = user_library
        self._quota = quota
        self._cache = cache
        self._cfg = config
        self._authenticated = is_authenticated

    async def recommend(
        self,
        limit: int = 10,
        topic_filter: Optional[str] = None,
        max_duration_seconds: Optional[int] = None,
    ) -> dict[str, object]:
        """FR-2.1 to FR-2.7: recommend videos."""
        # FR-2.1: require auth
        if not self._authenticated:
            raise auth_required()

        # Quota check
        est = self._quota.estimate_search_workflow(
            search_calls=0, video_fetch_count=100
        )
        if not self._quota.can_afford(general=est["general"]):
            raise quota_budget_exceeded(est["general"], self._quota.general_remaining)

        # FR-2.2: build profile from liked videos, subs, playlist items
        liked = await self._library.get_liked_videos(max_results=1000)
        self._quota.consume("videos.list", max(1, len(liked) // 50 + 1))

        playlists = await self._library.get_playlists()
        self._quota.consume("playlists.list", 1)

        playlist_videos: list[VideoMetadata] = []
        for pl in playlists[:10]:  # sample first 10 playlists
            pid = str(pl.get("id", ""))
            if pid:
                items = await self._library.get_playlist_items(pid, max_results=50)
                self._quota.consume("playlistItems.list", 1)
                playlist_videos.extend(items)

        profile_videos = liked + playlist_videos

        # FR-2.6: empty profile → explanatory empty result, not error
        if not profile_videos:
            return {
                "recommendations": [],
                "note": (
                    "No liked videos, playlists or relevant content found in your profile. "
                    "Like some videos or add items to playlists to get recommendations. "
                    + NOT_WATCH_HISTORY_NOTE
                ),
                "cap_note": LIKED_VIDEO_CAP_NOTE,
            }

        # Build a synthetic seed from profile (average across all profile videos)
        # Use the most common category and language as the "seed"
        from collections import Counter
        cats = Counter(v.category_id for v in profile_videos if v.category_id)
        langs = Counter(v.language for v in profile_videos if v.language)
        top_cat = cats.most_common(1)[0][0] if cats else ""
        top_lang = langs.most_common(1)[0][0] if langs else ""

        # Build combined text corpus from profile
        corpus = " ".join(v.text_corpus() for v in profile_videos[:100])

        # Create a synthetic seed VideoMetadata
        from cerebra.domain.entities import VideoMetadata as VM
        synthetic_seed = VM(
            video_id="_profile_seed_",
            title=corpus[:500],
            description=corpus[500:1000],
            channel_id="",
            channel_title="",
            duration_seconds=600,
            category_id=top_cat,
            language=top_lang,
            tags=[],
        )

        # Get candidates — search using top topics
        top_tags = []
        for v in profile_videos[:20]:
            top_tags.extend(v.tags[:3])
        query = " ".join(list(dict.fromkeys(top_tags))[:10]) or "educational"
        if topic_filter:
            query = topic_filter + " " + query

        candidates = await self._video.search_videos(query=query, max_results=50)
        self._quota.consume("search.list", 1)

        # FR-2.4: exclude already-liked or already-playlisted
        exclude_ids = {v.video_id for v in profile_videos}
        candidates = [c for c in candidates if c.video_id not in exclude_ids]

        # FR-2.7: optional filters
        if max_duration_seconds is not None:
            candidates = [c for c in candidates if c.duration_seconds <= max_duration_seconds]

        # FR-2.3: rank by similarity to profile
        scored = rank_videos(synthetic_seed, candidates)
        limit = max(1, min(limit, self._cfg.max_result_limit))

        recommendations = []
        for rank_i, sr in enumerate(scored[:limit], start=1):
            orig = next((c for c in candidates if c.video_id == sr.video_id), None)
            if orig is None:
                continue
            # FR-2.5: short reason
            reason = "Matches your viewing interests based on liked videos and playlists"
            if topic_filter and topic_filter.lower() in orig.title.lower():
                reason = f"Directly matches your topic filter: [DATA] {topic_filter}"
            recommendations.append({
                "rank": rank_i,
                "video_id": orig.video_id,
                "title": f"[DATA] {orig.title}",
                "channel": f"[DATA] {orig.channel_title}",
                "duration": orig.duration_human(),
                "duration_seconds": orig.duration_seconds,
                "url": orig.url,
                "score": round(sr.score, 4),
                "reason": reason,
                "tags_missing": sr.tags_missing,
            })

        return {
            "recommendations": recommendations,
            "note": NOT_WATCH_HISTORY_NOTE,
            "cap_note": LIKED_VIDEO_CAP_NOTE,
        }
