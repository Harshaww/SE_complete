"""Unit tests for domain/normalise.py (FR-1.1, FR-1.2)."""
import pytest

from cerebra.domain.errors import CerebraError, ErrorCode
from cerebra.domain.normalise import normalise_video_ref, normalise_channel_ref


# ── Video ID normalisation ────────────────────────────────────────────────────

class TestNormaliseVideoRef:
    def test_plain_video_id_accepted(self):
        assert normalise_video_ref("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_watch_url_extracted(self):
        assert normalise_video_ref("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_watch_url_with_extra_params(self):
        assert normalise_video_ref("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert normalise_video_ref("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_youtu_be_url(self):
        assert normalise_video_ref("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_youtu_be_no_scheme(self):
        assert normalise_video_ref("youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_embed_url(self):
        assert normalise_video_ref("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_strips_whitespace(self):
        assert normalise_video_ref("  dQw4w9WgXcQ  ") == "dQw4w9WgXcQ"

    def test_empty_raises_invalid_video_id(self):
        with pytest.raises(CerebraError) as exc:
            normalise_video_ref("")
        assert exc.value.code == ErrorCode.INVALID_VIDEO_ID

    def test_too_short_raises(self):
        with pytest.raises(CerebraError) as exc:
            normalise_video_ref("short")
        assert exc.value.code == ErrorCode.INVALID_VIDEO_ID

    def test_too_long_raises(self):
        with pytest.raises(CerebraError) as exc:
            normalise_video_ref("a" * 12)
        assert exc.value.code == ErrorCode.INVALID_VIDEO_ID

    def test_invalid_chars_raises(self):
        with pytest.raises(CerebraError) as exc:
            normalise_video_ref("dQw4w9Wg!cQ")
        assert exc.value.code == ErrorCode.INVALID_VIDEO_ID

    def test_no_api_call_on_rejection(self):
        """FR-1.2: malformed refs rejected WITHOUT calling the YouTube API.

        The normaliser is pure-domain: it raises CerebraError before any
        I/O, so no patch is needed — if this raises immediately, no network
        call occurred (the function has no network code at all).

        Note: "not-a-video" is exactly 11 chars from [A-Za-z0-9_-] so it IS
        a syntactically valid video ID.  Use a ref with an illegal character.
        """
        # "not_valid!!" contains '!' which is not in [A-Za-z0-9_-] → rejected.
        with pytest.raises(CerebraError) as exc:
            normalise_video_ref("not_valid!!")
        assert exc.value.code == ErrorCode.INVALID_VIDEO_ID


# ── Channel reference normalisation ──────────────────────────────────────────

class TestNormaliseChannelRef:
    def test_channel_id_accepted(self):
        kind, val = normalise_channel_ref("UCuAXFkgsw1L7xaCfnd5JJOw")
        assert kind == "id"
        assert val == "UCuAXFkgsw1L7xaCfnd5JJOw"

    def test_handle_at_accepted(self):
        kind, val = normalise_channel_ref("@mkbhd")
        assert kind == "handle"
        assert val == "mkbhd"

    def test_channel_url(self):
        kind, val = normalise_channel_ref("https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw")
        assert kind == "id"
        assert val == "UCuAXFkgsw1L7xaCfnd5JJOw"

    def test_handle_url(self):
        kind, val = normalise_channel_ref("https://www.youtube.com/@mkbhd")
        assert kind == "handle"
        assert val == "mkbhd"

    def test_custom_url(self):
        kind, val = normalise_channel_ref("https://www.youtube.com/c/mkbhd")
        assert kind == "custom"
        assert val == "mkbhd"

    def test_user_url(self):
        kind, val = normalise_channel_ref("https://www.youtube.com/user/mkbhd")
        assert kind == "user"
        assert val == "mkbhd"

    def test_empty_raises(self):
        with pytest.raises(CerebraError) as exc:
            normalise_channel_ref("")
        assert exc.value.code == ErrorCode.INVALID_CHANNEL_REF

    def test_malformed_raises(self):
        with pytest.raises(CerebraError) as exc:
            normalise_channel_ref("not_a_channel_ref!@#")
        assert exc.value.code == ErrorCode.INVALID_CHANNEL_REF
