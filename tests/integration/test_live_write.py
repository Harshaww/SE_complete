"""LIVE write test: creates exactly ONE private test playlist (manual workflow only).

Runs only from .github/workflows/live-api-write.yml after a human types the confirmation phrase
(workflow_dispatch input), against a dedicated throwaway account. Skipped everywhere else, so PR
CI never writes to YouTube (NFR-TE-1, NFR-SA-1, AGENTS rules 2 and 9).

It exercises the REAL write path end to end: persisted proposal -> CLI approval record bound to
digest + account -> create_playlist -> playlists.insert + playlistItems.insert (the only two
write methods, NFR-SA-2). It never edits or deletes anything. The playlist is private and named
CEREBRA-CI-TEST-<run id>; the human owner of the test account removes it manually.
"""

# mark: FR-4.5, FR-4.6, FR-4.8, FR-4.9, FR-5.1, NFR-SA-1, NFR-SA-2, NFR-SA-3, TR-5
from __future__ import annotations

import datetime
import io
import os
import uuid

import pytest

from cerebra.application.playlist import compute_digest
from cerebra.cli import main as cli_main
from cerebra.domain.entities import PlaylistItem, PlaylistProposal, PrivacyStatus, ProposalState
from cerebra.domain.errors import CerebraError
from cerebra.infrastructure.auth.oauth_manager import SCOPE_WRITE
from tests.support.helpers import run
from tests.support.live_real import STABLE_PUBLIC_VIDEO, build_live_container, live_env_missing

_SKIP = live_env_missing(write=True)
pytestmark = [
    pytest.mark.live_write,
    pytest.mark.skipif(bool(_SKIP), reason=_SKIP or "live write env available"),
]


def exercise_write_path(c, run_id: str) -> str:
    """Drive the real write path on container ``c``; returns the created playlist id.

    Shared by the live test below and by a double-backed dry run in CI
    (tests/integration/test_live_write_dryrun.py), so the flow is verified without network.
    """
    assert c.oauth is not None and c.live_adapter is not None and c.proposal_store is not None
    assert c.clock is not None
    assert c.oauth.has_scope(SCOPE_WRITE), "test token must carry the write scope"

    title = f"CEREBRA-CI-TEST-{run_id}"

    # One real, public, 19-second video: the whole playlist is a single item.
    video = run(c.live_adapter.get_video(STABLE_PUBLIC_VIDEO))
    item = PlaylistItem(video.video_id, video.title, video.channel_title, video.duration_seconds)
    account_id = run(c.live_adapter.get_account_id())

    proposal_id = str(uuid.uuid4())
    digest = compute_digest(proposal_id, title, [item.video_id], account_id)
    now = c.clock.utcnow_timestamp()
    expires = datetime.datetime.fromtimestamp(now + 900, tz=datetime.UTC).isoformat()
    c.proposal_store.save(
        PlaylistProposal(
            proposal_id=proposal_id,
            topic=title,
            total_duration_seconds=item.duration_seconds,
            max_video_duration_seconds=None,
            language=None,
            items=[item],
            created_at=c.clock.utcnow_iso(),
            expires_at=expires,
            state=ProposalState.PROPOSED,
            digest=digest,
            privacy_status=PrivacyStatus.PRIVATE,
            quota_reservation_general=100,
            quota_reservation_write=100,
            account_id=account_id,
        )
    )

    # The workflow_dispatch confirmation phrase is the human approval for this run. It is
    # recorded through the real `cerebra-cli approve` code path (digest re-typed, bound to account).
    out, err = io.StringIO(), io.StringIO()
    code = cli_main(
        ["approve", proposal_id],
        container_factory=lambda: c,
        input_fn=lambda prompt: digest[:8],
        isatty=lambda: True,
        out=out,
        err=err,
    )
    assert code == 0, err.getvalue()

    result = run(c.create_pl.create(proposal_id, digest, "private"))
    assert result["status"] == "CREATED", result
    playlist_id = str(result["playlist_id"])
    assert playlist_id and result["video_count"] == 1

    # Read it back from YouTube: it exists, carries our name and is private (FR-4.9).
    mine = {p["id"]: p for p in run(c.live_adapter.get_playlists())}
    assert playlist_id in mine
    assert mine[playlist_id]["title"] == title
    assert mine[playlist_id]["privacy_status"] == "private"

    # Single-use: the same approval cannot create a second playlist (FR-4.7).
    with pytest.raises(CerebraError):
        run(c.create_pl.create(proposal_id, digest, "private"))
    return playlist_id


def test_create_private_test_playlist(tmp_path):
    c = build_live_container(tmp_path, budget=2000)
    exercise_write_path(c, os.environ.get("GITHUB_RUN_ID", "local"))
