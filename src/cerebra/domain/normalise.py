"""Reference normalisation – FR-1.1, FR-1.2.

Accepts video URLs/IDs and channel URLs/handles/IDs.
Normalises to plain video_id or channel_id.
Rejects malformed references BEFORE any API call.
"""

from __future__ import annotations

import re

from cerebra.domain.errors import (
    invalid_channel_ref,
    invalid_video_id,
)

# ── Video ──────────────────────────────────────────────────────────────────────
# YouTube video IDs are exactly 11 characters: [A-Za-z0-9_-]
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# URL patterns that contain the video ID
_WATCH_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/watch\?.*?v=([A-Za-z0-9_-]{11})")
_SHORT_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([A-Za-z0-9_-]{11})")
_YOUTU_BE_RE = re.compile(r"(?:https?://)?youtu\.be/([A-Za-z0-9_-]{11})")
_EMBED_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/embed/([A-Za-z0-9_-]{11})")

# ── Channel ────────────────────────────────────────────────────────────────────
# Channel IDs start with "UC" followed by 22 base64url chars (total 24)
_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
# Handles: @username (1-30 chars, alphanumeric + _ . -)
_HANDLE_RE = re.compile(r"^@[A-Za-z0-9_.\\-]{1,30}$")

_CHANNEL_ID_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?youtube\.com/channel/(UC[A-Za-z0-9_-]{22})"
)
_HANDLE_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/@([A-Za-z0-9_.\\-]{1,30})")
_CUSTOM_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/c/([A-Za-z0-9_.\\-]{1,100})")
_USER_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/user/([A-Za-z0-9_.\\-]{1,100})")


def normalise_video_ref(ref: str) -> str:
    """Return the 11-char video ID or raise CerebraError (FR-1.1, FR-1.2).

    Does NOT call the YouTube API.
    """
    ref = ref.strip()
    if not ref:
        raise invalid_video_id(ref)

    # Already a plain ID
    if _VIDEO_ID_RE.match(ref):
        return ref

    # Try URL patterns in priority order
    for pattern in (_WATCH_URL_RE, _SHORT_URL_RE, _YOUTU_BE_RE, _EMBED_URL_RE):
        m = pattern.search(ref)
        if m:
            return m.group(1)

    raise invalid_video_id(ref)


def normalise_channel_ref(ref: str) -> tuple[str, str]:
    """Return (kind, value) for channel reference or raise CerebraError (FR-1.1, FR-1.2).

    kind ∈ {"id", "handle", "custom", "user"}
    Does NOT call the YouTube API.
    """
    ref = ref.strip()
    if not ref:
        raise invalid_channel_ref(ref)

    # Plain channel ID
    if _CHANNEL_ID_RE.match(ref):
        return ("id", ref)

    # @handle (bare)
    if _HANDLE_RE.match(ref):
        return ("handle", ref[1:])  # strip @

    # URL with channel ID
    m = _CHANNEL_ID_URL_RE.search(ref)
    if m:
        return ("id", m.group(1))

    # URL with @handle
    m = _HANDLE_URL_RE.search(ref)
    if m:
        return ("handle", m.group(1))

    # URL with /c/
    m = _CUSTOM_URL_RE.search(ref)
    if m:
        return ("custom", m.group(1))

    # URL with /user/
    m = _USER_URL_RE.search(ref)
    if m:
        return ("user", m.group(1))

    raise invalid_channel_ref(ref)
