"""Dry run of the live write flow against the in-memory YouTube double (no network).

Proves the exact sequence used by test_live_write.py (proposal -> CLI approval -> create ->
read-back -> single-use) is correct, so the manual live run only has to prove the real API.
"""

# mark: FR-4.5, FR-4.6, FR-4.8, FR-4.9, NFR-SA-1, NFR-SA-2, TR-5
from __future__ import annotations

from cerebra.domain.entities import VideoMetadata
from tests.integration.test_live_write import exercise_write_path
from tests.support.fake_youtube import FakeYouTube
from tests.support.live_env import CHANNEL, make_env, py_channel, python_catalog
from tests.support.live_real import STABLE_PUBLIC_VIDEO


def test_write_flow_against_double(tmp_path):
    zoo = VideoMetadata(
        STABLE_PUBLIC_VIDEO, "Me at the zoo", "", CHANNEL, "jawed", 19, "22", "en", [], True, "", ""
    )
    fake = FakeYouTube([*python_catalog(), zoo], [py_channel()])
    env = make_env(tmp_path, fake)

    playlist_id = exercise_write_path(env.container, "dryrun")

    # Only the two permitted write methods were used (NFR-SA-2), exactly once each.
    methods = [m for m in fake.method_names() if m.endswith(".insert")]
    assert sorted(methods) == ["playlistItems.insert", "playlists.insert"], methods
    assert playlist_id
