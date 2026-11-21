"""Domain entities – pure data, no I/O (FR-1.3, FR-1.6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DurationBand(str, Enum):
    """Duration bands (TBD-7 resolved: short<4min, medium 4-20min, long>20min)."""

    SHORT = "short"  # < 240 s
    MEDIUM = "medium"  # 240–1200 s
    LONG = "long"  # > 1200 s

    @classmethod
    def from_seconds(cls, seconds: int) -> DurationBand:
        if seconds < 240:
            return cls.SHORT
        elif seconds <= 1200:
            return cls.MEDIUM
        return cls.LONG


class ProposalState(str, Enum):
    """Proposal state machine (SRS B.3)."""

    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    PARTIAL = "PARTIAL"
    CREATED = "CREATED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

    def is_terminal(self) -> bool:
        return self in (
            ProposalState.CREATED,
            ProposalState.EXPIRED,
            ProposalState.CANCELLED,
            ProposalState.FAILED,
        )

    def allowed_transitions(self) -> frozenset[ProposalState]:
        _transitions: dict[ProposalState, frozenset[ProposalState]] = {
            ProposalState.PROPOSED: frozenset(
                {
                    ProposalState.CONFIRMED,
                    ProposalState.EXPIRED,
                    ProposalState.CANCELLED,
                }
            ),
            ProposalState.CONFIRMED: frozenset(
                {
                    ProposalState.CREATED,
                    ProposalState.PARTIAL,
                    ProposalState.FAILED,
                }
            ),
            ProposalState.PARTIAL: frozenset(
                {
                    ProposalState.CREATED,
                }
            ),
            ProposalState.CREATED: frozenset(),
            ProposalState.EXPIRED: frozenset(),
            ProposalState.CANCELLED: frozenset(),
            ProposalState.FAILED: frozenset(),
        }
        return _transitions[self]

    def can_transition_to(self, next_state: ProposalState) -> bool:
        return next_state in self.allowed_transitions()


class PrivacyStatus(str, Enum):
    PRIVATE = "private"
    PUBLIC = "public"
    UNLISTED = "unlisted"


@dataclass(frozen=True)
class VideoMetadata:
    """Metadata for a single YouTube video (FR-1.3)."""

    video_id: str
    title: str
    description: str
    channel_id: str
    channel_title: str
    duration_seconds: int
    category_id: str
    language: str  # e.g. "en", "" if unknown
    tags: list[str] = field(default_factory=list)
    tags_missing: bool = False
    thumbnail_url: str = ""
    published_at: str = ""  # ISO 8601 datetime

    @property
    def duration_band(self) -> DurationBand:
        return DurationBand.from_seconds(self.duration_seconds)

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    def duration_human(self) -> str:
        """Return duration as mm:ss or h:mm:ss (NFR-US-2)."""
        s = self.duration_seconds
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m}:{sec:02d}"

    def text_corpus(self) -> str:
        """Combined text for TF-IDF (FR-1.5)."""
        parts = [self.title, self.description]
        parts.extend(self.tags)
        return " ".join(parts)


@dataclass(frozen=True)
class ChannelMetadata:
    """Metadata for a YouTube channel (FR-1.3)."""

    channel_id: str
    title: str
    description: str
    keywords: list[str] = field(default_factory=list)
    topic_categories: list[str] = field(default_factory=list)
    language: str = ""
    subscriber_count: int | None = None
    upload_cadence_per_month: float = 0.0
    recent_upload_titles: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/channel/{self.channel_id}"

    def text_corpus(self) -> str:
        parts = [self.title, self.description]
        parts.extend(self.keywords)
        parts.extend(self.recent_upload_titles)
        return " ".join(parts)


@dataclass(frozen=True)
class SimilarVideo:
    """A ranked similar video result (FR-1.6)."""

    rank: int
    video_id: str
    title: str
    channel_title: str
    duration_seconds: int
    score: float
    tags_missing: bool
    url: str

    def duration_human(self) -> str:
        s = self.duration_seconds
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m}:{sec:02d}"


@dataclass(frozen=True)
class SimilarChannel:
    """A ranked similar channel result (FR-1.6)."""

    rank: int
    channel_id: str
    title: str
    score: float
    subscriber_count: int | None
    url: str


@dataclass(frozen=True)
class PlaylistItem:
    """A video in a proposed/created playlist."""

    video_id: str
    title: str
    channel_title: str
    duration_seconds: int

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    def duration_human(self) -> str:
        s = self.duration_seconds
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m}:{sec:02d}"


@dataclass
class PlaylistProposal:
    """A proposed playlist awaiting confirmation (FR-4.4, B.3)."""

    proposal_id: str
    topic: str
    total_duration_seconds: int
    max_video_duration_seconds: int | None
    language: str | None
    items: list[PlaylistItem]
    created_at: str  # ISO 8601 datetime
    expires_at: str  # ISO 8601 datetime
    state: ProposalState
    digest: str  # SHA-256 of canonical proposal content
    privacy_status: PrivacyStatus = PrivacyStatus.PRIVATE
    # Quota reservation
    quota_reservation_general: int = 0
    quota_reservation_write: int = 0
    # Created playlist info (populated after creation)
    playlist_id: str | None = None
    playlist_url: str | None = None
    failed_item_ids: list[str] = field(default_factory=list)
    # ADR-C: per-item write state (video_id -> PENDING | INSERTED | FAILED), persisted
    # BEFORE each write so a crash can be reconciled against remote state.
    item_states: dict[str, str] = field(default_factory=dict)
    # ADR-C §6: True when a write ended in an ambiguous failure (5xx / timeout).
    ambiguous: bool = False
    # ADR-A §2: account the proposal was bound to (empty in fixture mode).
    account_id: str = ""

    @property
    def total_actual_seconds(self) -> int:
        return sum(item.duration_seconds for item in self.items)

    def total_duration_human(self) -> str:
        s = self.total_actual_seconds
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f"{h}h {m}m {sec}s" if h else f"{m}m {sec}s"
