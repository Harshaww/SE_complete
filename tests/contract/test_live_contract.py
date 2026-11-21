"""LSP contract tests: the LIVE adapter (against an in-memory API double) must satisfy exactly
the same port contracts as the fixture adapter (NFR-MA-1, CON-6, Phase 3 item 4).

Video + writer contracts are the existing suites from test_contract.py, re-run here against
LiveYouTubeAdapter. Channel + user-library contracts are new and run against BOTH adapters.
"""

# mark: FR-5.17, CON-6
from __future__ import annotations

import pytest

from cerebra.adapters.fixtures.fixture_adapter import (
    FixtureChannelReader,
    FixtureUserLibraryReader,
)
from cerebra.domain.entities import ChannelMetadata, VideoMetadata
from cerebra.domain.errors import CerebraError, ErrorCode
from cerebra.ports.interfaces import (
    PlaylistWriter,
    PublicChannelReader,
    PublicVideoReader,
    UserLibraryReader,
)
from tests.contract.test_contract import PlaylistWriterContractTests, VideoReaderContractTests
from tests.support.fake_youtube import fixture_backed_fake
from tests.support.helpers import make_live, run

RICK_CHANNEL = "UCuAXFkgsw1L7xaCfnd5JJOw"


def _live():
    adapter, _q, _a, _s = make_live(fixture_backed_fake())
    return adapter


# ── existing suites, now against the live adapter ────────────────────────────


# mark: FR-5.17, CON-6
class TestLiveVideoReaderContract(VideoReaderContractTests):
    @pytest.fixture
    def reader(self):
        return _live()


# mark: FR-5.17, CON-6
class TestLivePlaylistWriterContract(PlaylistWriterContractTests):
    @pytest.fixture
    def writer(self):
        return _live()


# ── new suites run against both adapters ─────────────────────────────────────


class ChannelReaderContractTests:
    @pytest.fixture
    def reader(self):
        raise NotImplementedError

    def test_get_known_channel(self, reader):
        c = run(reader.get_channel(RICK_CHANNEL))
        assert isinstance(c, ChannelMetadata)
        assert c.channel_id == RICK_CHANNEL
        assert c.title

    def test_unknown_channel_raises_not_found(self, reader):
        with pytest.raises(CerebraError) as exc:
            run(reader.get_channel("UCzzzzzzzzzzzzzzzzzzzzzz"))
        assert exc.value.code == ErrorCode.CHANNEL_NOT_FOUND

    def test_resolve_id(self, reader):
        assert run(reader.resolve_channel("id", RICK_CHANNEL)) == RICK_CHANNEL

    def test_resolve_unknown_id_raises(self, reader):
        with pytest.raises(CerebraError) as exc:
            run(reader.resolve_channel("id", "UCzzzzzzzzzzzzzzzzzzzzzz"))
        assert exc.value.code == ErrorCode.CHANNEL_NOT_FOUND

    def test_search_channels_returns_list_of_metadata(self, reader):
        res = run(reader.search_channels("rick", max_results=5))
        assert isinstance(res, list)
        assert all(isinstance(c, ChannelMetadata) for c in res)


# mark: FR-5.17, CON-6
class TestFixtureChannelReaderContract(ChannelReaderContractTests):
    @pytest.fixture
    def reader(self):
        return FixtureChannelReader()


# mark: FR-5.17, CON-6
class TestLiveChannelReaderContract(ChannelReaderContractTests):
    @pytest.fixture
    def reader(self):
        return _live()


class UserLibraryContractTests:
    @pytest.fixture
    def library(self):
        raise NotImplementedError

    def test_liked_videos_is_list_of_metadata_and_respects_limit(self, library):
        res = run(library.get_liked_videos(max_results=2))
        assert isinstance(res, list) and len(res) <= 2
        assert all(isinstance(v, VideoMetadata) for v in res)

    def test_subscriptions_is_list_of_channels(self, library):
        res = run(library.get_subscriptions(max_results=5))
        assert isinstance(res, list)
        assert all(isinstance(c, ChannelMetadata) for c in res)

    def test_playlists_is_list_of_dicts_with_id(self, library):
        res = run(library.get_playlists())
        assert isinstance(res, list)
        assert all(isinstance(p, dict) and "id" in p for p in res)

    def test_playlist_items_for_unknown_playlist_does_not_return_garbage(self, library):
        try:
            res = run(library.get_playlist_items("PLdoesnotexist0000"))
        except CerebraError:
            return  # raising a structured error is acceptable
        assert res == []


# mark: FR-5.17, CON-6
class TestFixtureUserLibraryContract(UserLibraryContractTests):
    @pytest.fixture
    def library(self):
        return FixtureUserLibraryReader()


# mark: FR-5.17, CON-6
class TestLiveUserLibraryContract(UserLibraryContractTests):
    @pytest.fixture
    def library(self):
        return _live()


# ── structural (Protocol) conformance ────────────────────────────────────────


# mark: FR-5.17, CON-6
class TestLiveAdapterSatisfiesAllPorts:
    def test_isinstance_of_every_port(self):
        live = _live()
        assert isinstance(live, PublicVideoReader)
        assert isinstance(live, PublicChannelReader)
        assert isinstance(live, UserLibraryReader)
        assert isinstance(live, PlaylistWriter)
