"""Domain errors – structured, uniform (FR-5.15).

Every error has: code (str), message (str), retryable (bool), suggested_action (str).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorCode(str, Enum):
    # Reference validation
    INVALID_VIDEO_ID = "INVALID_VIDEO_ID"
    INVALID_CHANNEL_REF = "INVALID_CHANNEL_REF"
    VIDEO_NOT_FOUND_OR_PRIVATE = "VIDEO_NOT_FOUND_OR_PRIVATE"
    CHANNEL_NOT_FOUND = "CHANNEL_NOT_FOUND"
    # Auth
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    INSUFFICIENT_SCOPE = "INSUFFICIENT_SCOPE"
    # Quota
    QUOTA_BUDGET_EXCEEDED = "QUOTA_BUDGET_EXCEEDED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    # Proposal / playlist
    PROPOSAL_NOT_FOUND = "PROPOSAL_NOT_FOUND"
    PROPOSAL_EXPIRED = "PROPOSAL_EXPIRED"
    PROPOSAL_ALREADY_USED = "PROPOSAL_ALREADY_USED"
    PROPOSAL_INVALID_STATE = "PROPOSAL_INVALID_STATE"
    MISSING_CONSTRAINT = "MISSING_CONSTRAINT"
    PLAYLIST_INFEASIBLE = "PLAYLIST_INFEASIBLE"
    NO_YOUTUBE_CHANNEL = "NO_YOUTUBE_CHANNEL"
    PARTIAL_CREATION = "PARTIAL_CREATION"
    # Input
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    # Network / API
    TRANSIENT_ERROR = "TRANSIENT_ERROR"
    YOUTUBE_API_ERROR = "YOUTUBE_API_ERROR"
    # Security
    APPROVAL_REJECTED = "APPROVAL_REJECTED"


@dataclass(frozen=True)
class CerebraError(Exception):
    """Uniform structured error (FR-5.15)."""

    code: ErrorCode
    message: str
    retryable: bool = False
    suggested_action: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "retryable": self.retryable,
                "suggested_action": self.suggested_action,
            }
        }


# Convenience factories
def invalid_video_id(ref: str) -> CerebraError:
    return CerebraError(
        ErrorCode.INVALID_VIDEO_ID,
        f"[DATA] The reference {ref!r} is not a valid YouTube video URL or ID.",
        suggested_action="Provide an 11-character video ID or a valid YouTube watch/short/youtu.be URL.",
    )


def invalid_channel_ref(ref: str) -> CerebraError:
    return CerebraError(
        ErrorCode.INVALID_CHANNEL_REF,
        f"[DATA] The reference {ref!r} is not a valid YouTube channel URL, handle or ID.",
        suggested_action="Provide a /channel/, /@handle or /c/ URL, a @handle, or a 24-character channel ID.",
    )


def video_not_found(video_id: str) -> CerebraError:
    return CerebraError(
        ErrorCode.VIDEO_NOT_FOUND_OR_PRIVATE,
        f"Video {video_id!r} was not found or is private.",
        suggested_action="Check the video ID or try a different video.",
    )


def channel_not_found(channel_id: str) -> CerebraError:
    return CerebraError(
        ErrorCode.CHANNEL_NOT_FOUND,
        f"Channel {channel_id!r} was not found.",
        suggested_action="Check the channel ID or handle.",
    )


def auth_required() -> CerebraError:
    return CerebraError(
        ErrorCode.AUTH_REQUIRED,
        "This tool requires YouTube authorisation. Please authorise first.",
        suggested_action="Run the authorise command to connect your YouTube account.",
    )


def auth_expired() -> CerebraError:
    return CerebraError(
        ErrorCode.AUTH_EXPIRED,
        "Your YouTube authorisation has expired or been revoked.",
        suggested_action="Re-authorise your YouTube account.",
    )


def quota_budget_exceeded(estimated: int, remaining: int) -> CerebraError:
    return CerebraError(
        ErrorCode.QUOTA_BUDGET_EXCEEDED,
        f"This workflow needs ~{estimated} quota units but only {remaining} remain today.",
        suggested_action="Wait until midnight Pacific Time for quota reset, or reduce the request size.",
    )


def quota_exhausted(reset_at: str) -> CerebraError:
    return CerebraError(
        ErrorCode.QUOTA_EXHAUSTED,
        f"YouTube API daily quota is exhausted. Resets at {reset_at} Pacific Time.",
        retryable=False,
        suggested_action="Wait for quota reset at midnight Pacific Time.",
    )


def proposal_not_found(proposal_id: str) -> CerebraError:
    return CerebraError(
        ErrorCode.PROPOSAL_NOT_FOUND,
        f"Proposal {proposal_id!r} was not found.",
        suggested_action="Run propose_playlist again to create a new proposal.",
    )


def proposal_expired(proposal_id: str) -> CerebraError:
    return CerebraError(
        ErrorCode.PROPOSAL_EXPIRED,
        f"Proposal {proposal_id!r} has expired (proposals expire after 15 minutes).",
        suggested_action="Run propose_playlist again to create a new proposal.",
    )


def proposal_already_used(proposal_id: str) -> CerebraError:
    return CerebraError(
        ErrorCode.PROPOSAL_ALREADY_USED,
        f"Proposal {proposal_id!r} has already been used.",
        suggested_action="A playlist was already created from this proposal. Run propose_playlist again if you want another.",
    )


def missing_constraint(fields: list[str]) -> CerebraError:
    return CerebraError(
        ErrorCode.MISSING_CONSTRAINT,
        f"The following mandatory constraints are missing: {', '.join(fields)}.",
        suggested_action="Please provide: " + " and ".join(fields) + ".",
    )


def no_youtube_channel() -> CerebraError:
    return CerebraError(
        ErrorCode.NO_YOUTUBE_CHANNEL,
        "Your Google account does not have a YouTube channel and cannot create playlists.",
        suggested_action="Go to youtube.com and create a channel first, then try again.",
    )


def invalid_argument(param: str, reason: str) -> CerebraError:
    return CerebraError(
        ErrorCode.INVALID_ARGUMENT,
        f"[DATA] Invalid value for parameter {param!r}: {reason}",
        suggested_action="Check the parameter value and try again.",
    )


def approval_rejected(reason: str) -> CerebraError:
    return CerebraError(
        ErrorCode.APPROVAL_REJECTED,
        f"Playlist creation was not approved: {reason}",
        suggested_action="Confirm the playlist proposal explicitly through the confirmation prompt.",
    )


def transient_error(detail: str) -> CerebraError:
    return CerebraError(
        ErrorCode.TRANSIENT_ERROR,
        f"A transient error occurred: {detail}",
        retryable=True,
        suggested_action="The request will be retried automatically. If this persists, try again later.",
    )


def insufficient_scope(required: str) -> CerebraError:
    return CerebraError(
        ErrorCode.INSUFFICIENT_SCOPE,
        f"The current YouTube authorisation does not include the required scope: {required}.",
        suggested_action=(
            "Run `cerebra-cli login --write` in your terminal to grant write access, then retry."
        ),
    )


def youtube_api_error(status: int, reason: str) -> CerebraError:
    """Non-retryable YouTube API failure (4xx other than the mapped cases)."""
    return CerebraError(
        ErrorCode.YOUTUBE_API_ERROR,
        f"The YouTube API returned HTTP {status} ({reason or 'unknown reason'}).",
        retryable=False,
        suggested_action="Check the request parameters. If this persists, report it.",
    )
