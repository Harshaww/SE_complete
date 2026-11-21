"""In-memory stand-in for the googleapiclient YouTube v3 resource (tests only, NFR-TE-1).

It mimics the *shape* of the official client (``service.videos().list(**kw).execute()``) and
of the API's JSON responses, so LiveYouTubeAdapter runs unmodified against it and no network
is ever touched. Every call is recorded in ``calls`` so tests can assert on exactly which
official methods were invoked.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httplib2
from googleapiclient.errors import HttpError

from cerebra.domain.duration import seconds_to_iso8601
from cerebra.domain.entities import ChannelMetadata, VideoMetadata


def http_error(status: int, reason: str = "") -> HttpError:
    body = {"error": {"code": status, "errors": [{"reason": reason}]}}
    return HttpError(httplib2.Response({"status": str(status)}), json.dumps(body).encode())


def video_resource(v: VideoMetadata) -> dict[str, Any]:
    return {
        "id": v.video_id,
        "snippet": {
            "title": v.title,
            "description": v.description,
            "channelId": v.channel_id,
            "channelTitle": v.channel_title,
            "categoryId": v.category_id,
            "defaultAudioLanguage": v.language,
            "tags": list(v.tags),
            "publishedAt": v.published_at,
            "thumbnails": {
                "medium": {"url": v.thumbnail_url or f"https://i.ytimg.com/vi/{v.video_id}/mq.jpg"}
            },
        },
        "contentDetails": {"duration": seconds_to_iso8601(v.duration_seconds)},
    }


def channel_resource(c: ChannelMetadata, uploads: str | None = None) -> dict[str, Any]:
    kw = " ".join(f'"{k}"' if " " in k else k for k in c.keywords)
    return {
        "id": c.channel_id,
        "snippet": {"title": c.title, "description": c.description, "defaultLanguage": c.language},
        "statistics": {"subscriberCount": str(c.subscriber_count or 0)},
        "topicDetails": {
            "topicCategories": [f"https://en.wikipedia.org/wiki/{t}" for t in c.topic_categories]
        },
        "brandingSettings": {"channel": {"keywords": kw}},
        "contentDetails": {"relatedPlaylists": {"uploads": uploads or "UU" + c.channel_id[2:]}},
    }


class _Request:
    def __init__(self, fn: Callable[[], Any]) -> None:
        self._fn = fn

    def execute(self) -> Any:
        return self._fn()


class FakeYouTube:
    """Build with domain objects; behaves like ``googleapiclient.discovery.Resource``."""

    def __init__(
        self,
        videos: list[VideoMetadata],
        channels: list[ChannelMetadata],
        liked: list[VideoMetadata] | None = None,
        subscriptions: list[ChannelMetadata] | None = None,
        account_channel_id: str | None = "UCaccount0000000000000000",
    ) -> None:
        self.videos_by_id = {v.video_id: v for v in videos}
        self.channels_by_id = {c.channel_id: c for c in channels}
        self.handles = {c.title.lower().replace(" ", ""): c.channel_id for c in channels}
        self.liked = liked or []
        self.sub_list = subscriptions or []
        self.account_channel_id = account_channel_id
        self.pl_store: dict[str, dict[str, Any]] = {}
        self.playlist_videos: dict[str, list[dict[str, str]]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        # error injection: "playlists.insert" -> [exc, None, exc ...] consumed per call
        self.errors: dict[str, list[BaseException | None]] = {}
        # simulate an AMBIGUOUS failure: the write is applied remotely, then the call raises
        self.apply_then_fail: set[str] = set()
        self._n = 0

    # ── helpers ──────────────────────────────────────────────────────────────
    def method_names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def _call(
        self, name: str, kwargs: dict[str, Any], fn: Callable[[], Any], applies: bool = False
    ) -> _Request:
        def run() -> Any:
            self.calls.append((name, dict(kwargs)))
            queue = self.errors.get(name)
            exc = queue.pop(0) if queue else None
            if exc is not None and not (applies and name in self.apply_then_fail):
                raise exc
            result = fn()
            if exc is not None:
                raise exc
            return result

        return _Request(run)

    @staticmethod
    def _page(items: list[Any], kw: dict[str, Any]) -> dict[str, Any]:
        start = int(kw.get("pageToken") or 0)
        size = int(kw.get("maxResults") or 5)
        chunk = items[start : start + size]
        out: dict[str, Any] = {"items": chunk}
        if start + size < len(items):
            out["nextPageToken"] = str(start + size)
        return out

    # ── resources ────────────────────────────────────────────────────────────
    def videos(self) -> FakeYouTube._Videos:
        return FakeYouTube._Videos(self)

    def channels(self) -> FakeYouTube._Channels:
        return FakeYouTube._Channels(self)

    def search(self) -> FakeYouTube._Search:
        return FakeYouTube._Search(self)

    def playlistItems(self) -> FakeYouTube._PlaylistItems:
        return FakeYouTube._PlaylistItems(self)

    def playlists(self) -> FakeYouTube._Playlists:
        return FakeYouTube._Playlists(self)

    def subscriptions(self) -> FakeYouTube._Subs:
        return FakeYouTube._Subs(self)

    class _Videos:
        def __init__(self, o: FakeYouTube) -> None:
            self.o = o

        def list(self, **kw: Any) -> _Request:
            def fn() -> dict[str, Any]:
                if kw.get("myRating") == "like":
                    return self.o._page([video_resource(v) for v in self.o.liked], kw)
                ids = [i for i in str(kw.get("id", "")).split(",") if i]
                return {
                    "items": [
                        video_resource(self.o.videos_by_id[i])
                        for i in ids
                        if i in self.o.videos_by_id
                    ]
                }

            return self.o._call("videos.list", kw, fn)

    class _Channels:
        def __init__(self, o: FakeYouTube) -> None:
            self.o = o

        def list(self, **kw: Any) -> _Request:
            def fn() -> dict[str, Any]:
                if kw.get("mine"):
                    cid = self.o.account_channel_id
                    return {"items": [{"id": cid}] if cid else []}
                ids: list[str] = []
                if kw.get("id"):
                    ids = [i for i in str(kw["id"]).split(",") if i]
                elif kw.get("forHandle"):
                    h = str(kw["forHandle"]).lstrip("@").lower()
                    ids = [self.o.handles[h]] if h in self.o.handles else []
                elif kw.get("forUsername"):
                    ids = []
                return {
                    "items": [
                        channel_resource(self.o.channels_by_id[i])
                        for i in ids
                        if i in self.o.channels_by_id
                    ]
                }

            return self.o._call("channels.list", kw, fn)

    class _Search:
        def __init__(self, o: FakeYouTube) -> None:
            self.o = o

        def list(self, **kw: Any) -> _Request:
            def fn() -> dict[str, Any]:
                q = str(kw.get("q", "")).lower()
                if kw.get("type") == "channel":
                    hits = [
                        {"id": {"kind": "youtube#channel", "channelId": c.channel_id}}
                        for c in self.o.channels_by_id.values()
                        if q in c.title.lower() or q in c.description.lower()
                    ]
                else:
                    hits = [
                        {"id": {"kind": "youtube#video", "videoId": v.video_id}}
                        for v in self.o.videos_by_id.values()
                        if q in v.title.lower()
                        or q in v.description.lower()
                        or any(q in t.lower() for t in v.tags)
                    ]
                return self.o._page(hits, kw)

            return self.o._call("search.list", kw, fn)

    class _PlaylistItems:
        def __init__(self, o: FakeYouTube) -> None:
            self.o = o

        def list(self, **kw: Any) -> _Request:
            def fn() -> dict[str, Any]:
                pid = str(kw["playlistId"])
                if pid.startswith("UU"):  # uploads playlist of a channel
                    cid = "UC" + pid[2:]
                    items = [
                        {
                            "snippet": {"title": v.title, "publishedAt": v.published_at},
                            "contentDetails": {"videoId": v.video_id},
                        }
                        for v in self.o.videos_by_id.values()
                        if v.channel_id == cid
                    ]
                else:
                    if pid not in self.o.pl_store:
                        raise http_error(404, "playlistNotFound")
                    items = [
                        {
                            "snippet": {"publishedAt": e["added"]},
                            "contentDetails": {"videoId": e["video_id"]},
                        }
                        for e in self.o.playlist_videos.get(pid, [])
                    ]
                return self.o._page(items, kw)

            return self.o._call("playlistItems.list", kw, fn)

        def insert(self, **kw: Any) -> _Request:
            def fn() -> dict[str, Any]:
                sn = kw["body"]["snippet"]
                pid, vid = sn["playlistId"], sn["resourceId"]["videoId"]
                self.o.playlist_videos.setdefault(pid, []).append(
                    {"video_id": vid, "added": "2026-11-21T00:00:00Z"}
                )
                return {"id": f"item-{vid}"}

            return self.o._call("playlistItems.insert", kw, fn, applies=True)

    class _Playlists:
        def __init__(self, o: FakeYouTube) -> None:
            self.o = o

        def list(self, **kw: Any) -> _Request:
            def fn() -> dict[str, Any]:
                items = [
                    {
                        "id": pid,
                        "snippet": {
                            "title": p["snippet"]["title"],
                            "description": p["snippet"]["description"],
                            "publishedAt": "2026-11-21T00:00:00Z",
                        },
                        "contentDetails": {"itemCount": len(self.o.playlist_videos.get(pid, []))},
                        "status": p["status"],
                    }
                    for pid, p in self.o.pl_store.items()
                ]
                return self.o._page(items, kw)

            return self.o._call("playlists.list", kw, fn)

        def insert(self, **kw: Any) -> _Request:
            def fn() -> dict[str, Any]:
                self.o._n += 1
                pid = f"PLfake{self.o._n:08d}"
                self.o.pl_store[pid] = kw["body"]
                return {"id": pid}

            return self.o._call("playlists.insert", kw, fn, applies=True)

    class _Subs:
        def __init__(self, o: FakeYouTube) -> None:
            self.o = o

        def list(self, **kw: Any) -> _Request:
            def fn() -> dict[str, Any]:
                items = [
                    {
                        "snippet": {
                            "title": c.title,
                            "description": c.description,
                            "resourceId": {"channelId": c.channel_id},
                        }
                    }
                    for c in self.o.sub_list
                ]
                return self.o._page(items, kw)

            return self.o._call("subscriptions.list", kw, fn)


def fixture_backed_fake() -> FakeYouTube:
    """A FakeYouTube holding the same data as the fixture adapter (for LSP contract tests)."""
    from cerebra.adapters.fixtures.fixture_adapter import (
        FixtureChannelReader,
        FixtureUserLibraryReader,
        FixtureVideoReader,
    )

    v = FixtureVideoReader()
    c = FixtureChannelReader()
    lib = FixtureUserLibraryReader()
    return FakeYouTube(
        videos=list(v._videos.values()),
        channels=list(c._channels.values()),
        liked=lib._liked,
        subscriptions=lib._subscriptions,
    )
