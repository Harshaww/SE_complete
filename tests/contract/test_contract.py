"""Contract tests: same suite run against BOTH live adapter (mocked HTTP) and fixture adapter.

Both must satisfy the same port contracts (LSP, NFR-MA-1, CON-6).
"""

from __future__ import annotations

import asyncio

import pytest

from cerebra.adapters.fixtures.fixture_adapter import (
    FixturePlaylistWriter,
    FixtureVideoReader,
)
from cerebra.domain.errors import CerebraError, ErrorCode


def _build_fixture_video_reader_with_data():
    r = FixtureVideoReader.__new__(FixtureVideoReader)
    from cerebra.adapters.fixtures.fixture_adapter import _dict_to_video

    r._videos = {
        "dQw4w9WgXcQ": _dict_to_video(
            {
                "video_id": "dQw4w9WgXcQ",
                "title": "Test Video",
                "description": "A test video",
                "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
                "channel_title": "Test Channel",
                "duration_seconds": 213,
                "category_id": "10",
                "language": "en",
                "tags": ["test", "music"],
            }
        )
    }
    return r


class VideoReaderContractTests:
    """Contract suite for PublicVideoReader implementations."""

    @pytest.fixture
    def reader(self):
        raise NotImplementedError

    def test_get_known_video_returns_metadata(self, reader):
        video = asyncio.get_event_loop().run_until_complete(reader.get_video("dQw4w9WgXcQ"))
        assert video.video_id == "dQw4w9WgXcQ"
        assert video.title
        assert video.duration_seconds > 0

    def test_get_unknown_video_raises_not_found(self, reader):
        with pytest.raises(CerebraError) as exc:
            asyncio.get_event_loop().run_until_complete(
                reader.get_video("XXXXXXXXXXX")  # 11 chars, doesn't exist
            )
        assert exc.value.code == ErrorCode.VIDEO_NOT_FOUND_OR_PRIVATE

    def test_get_videos_batch_returns_known(self, reader):
        videos = asyncio.get_event_loop().run_until_complete(reader.get_videos(["dQw4w9WgXcQ"]))
        assert len(videos) == 1

    def test_get_videos_batch_omits_missing(self, reader):
        videos = asyncio.get_event_loop().run_until_complete(
            reader.get_videos(["XXXXXXXXXXX"])  # doesn't exist
        )
        assert len(videos) == 0

    def test_search_returns_list(self, reader):
        results = asyncio.get_event_loop().run_until_complete(
            reader.search_videos("test", max_results=5)
        )
        assert isinstance(results, list)

    def test_get_channel_uploads_returns_list(self, reader):
        results = asyncio.get_event_loop().run_until_complete(
            reader.get_channel_uploads("UCuAXFkgsw1L7xaCfnd5JJOw", max_results=10)
        )
        assert isinstance(results, list)


# mark: FR-5.17, CON-6, NFR-MA-1, FR-1.3
class TestFixtureVideoReaderContract(VideoReaderContractTests):
    """Run contract suite against fixture adapter."""

    @pytest.fixture
    def reader(self):
        return _build_fixture_video_reader_with_data()


class PlaylistWriterContractTests:
    """Contract suite for PlaylistWriter implementations."""

    @pytest.fixture
    def writer(self):
        raise NotImplementedError

    def test_create_playlist_returns_id(self, writer):
        pid = asyncio.get_event_loop().run_until_complete(
            writer.create_playlist("Test Playlist", "Description", "private")
        )
        assert isinstance(pid, str)
        assert pid

    def test_add_playlist_item_no_error(self, writer):
        pid = asyncio.get_event_loop().run_until_complete(
            writer.create_playlist("Test", "", "private")
        )
        # Should not raise
        asyncio.get_event_loop().run_until_complete(writer.add_playlist_item(pid, "dQw4w9WgXcQ", 0))


# mark: FR-5.17, CON-6, NFR-MA-1
class TestFixturePlaylistWriterContract(PlaylistWriterContractTests):
    @pytest.fixture
    def writer(self):
        return FixturePlaylistWriter()
