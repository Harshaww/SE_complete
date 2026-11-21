"""Fixture adapter – recorded API responses for CI (FR-5.17, CON-6, NFR-TE-1).

Satisfies the same port contracts as the live YouTube adapter (LSP).
No real YouTube HTTP calls ever made here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from cerebra.domain.entities import ChannelMetadata, PlaylistItem, VideoMetadata
from cerebra.domain.errors import channel_not_found, video_not_found
from cerebra.ports.interfaces import (
    PlaylistWriter,
    PublicChannelReader,
    PublicVideoReader,
    UserLibraryReader,
)

_FIXTURES_DIR = Path(__file__).parent.parent.parent.parent.parent / "tests" / "fixtures"


def _load_json(path: Path) -> object:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class FixtureVideoReader:
    """PublicVideoReader backed by JSON fixture files."""

    def __init__(self, fixture_dir: Optional[Path] = None) -> None:
        self._dir = fixture_dir or _FIXTURES_DIR / "videos"
        # In-memory index built from fixture files
        self._videos: dict[str, VideoMetadata] = {}
        self._load_all()

    def _load_all(self) -> None:
        if not self._dir.exists():
            return
        for f in self._dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                v = _dict_to_video(data)
                self._videos[v.video_id] = v
            except Exception:
                pass

    async def get_video(self, video_id: str) -> VideoMetadata:
        v = self._videos.get(video_id)
        if v is None:
            raise video_not_found(video_id)
        return v

    async def get_videos(self, video_ids: list[str]) -> list[VideoMetadata]:
        return [self._videos[vid] for vid in video_ids if vid in self._videos]

    async def search_videos(
        self,
        query: str,
        max_results: int = 25,
        language: Optional[str] = None,
    ) -> list[VideoMetadata]:
        q = query.lower()
        results = [
            v for v in self._videos.values()
            if q in v.title.lower() or q in v.description.lower()
            or any(q in t.lower() for t in v.tags)
        ]
        if language:
            results = [v for v in results if not v.language or v.language.lower() == language.lower()]
        return results[:max_results]

    async def get_channel_uploads(self, channel_id: str, max_results: int = 50) -> list[VideoMetadata]:
        return [v for v in self._videos.values() if v.channel_id == channel_id][:max_results]


class FixtureChannelReader:
    """PublicChannelReader backed by JSON fixture files."""

    def __init__(self, fixture_dir: Optional[Path] = None) -> None:
        self._dir = fixture_dir or _FIXTURES_DIR / "channels"
        self._channels: dict[str, ChannelMetadata] = {}
        self._handles: dict[str, str] = {}
        self._load_all()

    def _load_all(self) -> None:
        if not self._dir.exists():
            return
        for f in self._dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                c = _dict_to_channel(data)
                self._channels[c.channel_id] = c
                handle = data.get("handle", "")
                if handle:
                    self._handles[handle.lstrip("@")] = c.channel_id
            except Exception:
                pass

    async def get_channel(self, channel_id: str) -> ChannelMetadata:
        c = self._channels.get(channel_id)
        if c is None:
            raise channel_not_found(channel_id)
        return c

    async def resolve_channel(self, kind: str, value: str) -> str:
        if kind == "id":
            if value in self._channels:
                return value
            raise channel_not_found(value)
        if kind == "handle":
            cid = self._handles.get(value)
            if cid:
                return cid
        # Fallback: search by value in channel IDs
        raise channel_not_found(value)

    async def search_channels(self, query: str, max_results: int = 25) -> list[ChannelMetadata]:
        q = query.lower()
        return [
            c for c in self._channels.values()
            if q in c.title.lower() or q in c.description.lower()
        ][:max_results]


class FixtureUserLibraryReader:
    """UserLibraryReader backed by JSON fixture files."""

    def __init__(self, fixture_dir: Optional[Path] = None) -> None:
        self._dir = fixture_dir or _FIXTURES_DIR / "playlists"
        self._liked: list[VideoMetadata] = []
        self._subscriptions: list[ChannelMetadata] = []
        self._playlists: list[dict[str, object]] = []
        self._playlist_items: dict[str, list[VideoMetadata]] = {}
        self._load_all()

    def _load_all(self) -> None:
        if not self._dir.exists():
            return
        liked_path = self._dir / "liked_videos.json"
        if liked_path.exists():
            data = json.loads(liked_path.read_text(encoding="utf-8"))
            self._liked = [_dict_to_video(v) for v in data.get("items", [])]
        subs_path = self._dir / "subscriptions.json"
        if subs_path.exists():
            data = json.loads(subs_path.read_text(encoding="utf-8"))
            self._subscriptions = [_dict_to_channel(c) for c in data.get("items", [])]
        playlists_path = self._dir / "playlists.json"
        if playlists_path.exists():
            data = json.loads(playlists_path.read_text(encoding="utf-8"))
            self._playlists = data.get("items", [])
            for pl in self._playlists:
                pid = str(pl.get("id", ""))
                items_path = self._dir / f"playlist_{pid}_items.json"
                if items_path.exists():
                    items_data = json.loads(items_path.read_text(encoding="utf-8"))
                    self._playlist_items[pid] = [
                        _dict_to_video(v) for v in items_data.get("items", [])
                    ]

    async def get_liked_videos(self, max_results: int = 1000) -> list[VideoMetadata]:
        return self._liked[:max_results]

    async def get_subscriptions(self, max_results: int = 500) -> list[ChannelMetadata]:
        return self._subscriptions[:max_results]

    async def get_playlists(self, max_results: int = 200) -> list[dict[str, object]]:
        return self._playlists[:max_results]

    async def get_playlist_items(self, playlist_id: str, max_results: int = 500) -> list[VideoMetadata]:
        return self._playlist_items.get(playlist_id, [])[:max_results]


class FixturePlaylistWriter:
    """PlaylistWriter that records operations in memory (never calls YouTube)."""

    def __init__(self) -> None:
        self.created_playlists: list[dict[str, object]] = []
        self.added_items: list[dict[str, object]] = []
        self._next_id = 1
        # Optionally inject failures for testing
        self.fail_on_create: bool = False
        self.fail_on_item_ids: set[str] = set()

    async def ensure_write_access(self) -> None:
        """Fixture mode has no OAuth; write access is always 'available'."""
        return None

    async def create_playlist(
        self, title: str, description: str, privacy_status: str
    ) -> str:
        if self.fail_on_create:
            from cerebra.domain.errors import transient_error
            raise transient_error("Fixture-injected playlist creation failure")
        playlist_id = f"PLfixture{self._next_id:06d}"
        self._next_id += 1
        self.created_playlists.append({
            "id": playlist_id, "title": title,
            "description": description, "privacy_status": privacy_status,
        })
        return playlist_id

    async def add_playlist_item(
        self, playlist_id: str, video_id: str, position: int
    ) -> None:
        if video_id in self.fail_on_item_ids:
            from cerebra.domain.errors import transient_error
            raise transient_error(f"Fixture-injected item failure for {video_id}")
        self.added_items.append({
            "playlist_id": playlist_id, "video_id": video_id, "position": position
        })


# ── Helper converters ─────────────────────────────────────────────────────────

def _dict_to_video(d: dict[str, object]) -> VideoMetadata:
    tags = d.get("tags", [])
    return VideoMetadata(
        video_id=str(d.get("video_id", d.get("id", ""))),
        title=str(d.get("title", "")),
        description=str(d.get("description", "")),
        channel_id=str(d.get("channel_id", "")),
        channel_title=str(d.get("channel_title", "")),
        duration_seconds=int(d.get("duration_seconds", 0)),
        category_id=str(d.get("category_id", "")),
        language=str(d.get("language", "")),
        tags=list(tags) if isinstance(tags, list) else [],
        tags_missing=bool(d.get("tags_missing", not tags)),
        thumbnail_url=str(d.get("thumbnail_url", "")),
        published_at=str(d.get("published_at", "")),
    )


def _dict_to_channel(d: dict[str, object]) -> ChannelMetadata:
    return ChannelMetadata(
        channel_id=str(d.get("channel_id", d.get("id", ""))),
        title=str(d.get("title", "")),
        description=str(d.get("description", "")),
        keywords=list(d.get("keywords", [])),
        topic_categories=list(d.get("topic_categories", [])),
        language=str(d.get("language", "")),
        subscriber_count=d.get("subscriber_count"),  # type: ignore[arg-type]
        upload_cadence_per_month=float(d.get("upload_cadence_per_month", 0.0)),
        recent_upload_titles=list(d.get("recent_upload_titles", [])),
    )
