"""Application use case: propose_playlist + create_playlist (FR-4).

SAFETY CRITICAL: No write can happen without human-originated confirmation
bound to the proposal_id, digest, account, expiry, and single-use (FR-4.6, ADR-A).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Optional

from cerebra.config import Config
from cerebra.domain.entities import (
    PlaylistItem,
    PlaylistProposal,
    PrivacyStatus,
    ProposalState,
)
from cerebra.domain.errors import (
    CerebraError,
    approval_rejected,
    auth_required,
    missing_constraint,
    no_youtube_channel,
    proposal_already_used,
    proposal_expired,
    proposal_not_found,
    quota_budget_exceeded,
)
from cerebra.domain.playlist_solver import solve_playlist
from cerebra.domain.quota import QUOTA_COSTS, QuotaLedger
from cerebra.domain.state_machine import StateMachineError, transition
from cerebra.ports.interfaces import (
    AuditLog,
    CacheStore,
    Clock,
    PlaylistWriter,
    ProposalStore,
    PublicVideoReader,
)


class ProposePlaylistUseCase:
    """FR-4.1 to FR-4.5: propose a playlist without creating anything."""

    def __init__(
        self,
        video_reader: PublicVideoReader,
        quota: QuotaLedger,
        proposal_store: ProposalStore,
        cache: CacheStore,
        clock: Clock,
        config: Config,
        is_authenticated: bool = False,
    ) -> None:
        self._video = video_reader
        self._quota = quota
        self._proposal_store = proposal_store
        self._cache = cache
        self._clock = clock
        self._cfg = config
        self._authenticated = is_authenticated

    async def propose(
        self,
        topic: Optional[str],
        total_duration_seconds: Optional[int],
        max_video_duration_seconds: Optional[int] = None,
        language: Optional[str] = None,
    ) -> dict[str, object]:
        """FR-4.1 to FR-4.5."""
        if not self._authenticated:
            raise auth_required()

        # FR-4.1: check mandatory constraints
        missing = []
        if not topic:
            missing.append("topic")
        if total_duration_seconds is None:
            missing.append("total_duration_seconds")
        if missing:
            raise missing_constraint(missing)

        assert topic is not None
        assert total_duration_seconds is not None

        # FR-4.11: estimate WHOLE workflow cost before any API call
        max_items = min(50, total_duration_seconds // 60)  # rough upper bound
        est = self._quota.estimate_playlist_workflow(num_items=max_items)
        if not self._quota.can_afford(general=est["general"], search=est["search"]):
            raise quota_budget_exceeded(est["general"], self._quota.general_remaining)

        # Reserve quota atomically (ADR-B)
        reserved = self._quota.reserve(general=est["general"], search=est["search"])
        if not reserved:
            raise quota_budget_exceeded(est["general"], self._quota.general_remaining)

        try:
            # Build candidates
            candidates = await self._video.search_videos(
                query=topic, max_results=self._cfg.max_candidates, language=language
            )
            self._quota.consume("search.list", 1)

            # Apply language + max-duration hard constraints, then solve
            solver_result = solve_playlist(
                topic=topic,
                total_duration_seconds=total_duration_seconds,
                candidates=candidates,
                max_video_duration_seconds=max_video_duration_seconds,
                language=language,
                fill_ratio=self._cfg.playlist_fill_ratio,
            )

            # Create proposal
            now_iso = self._clock.utcnow_iso()
            expires_at = self._clock.utcnow_timestamp() + self._cfg.proposal_expiry_seconds

            import datetime
            expires_iso = datetime.datetime.fromtimestamp(
                expires_at, tz=datetime.timezone.utc
            ).isoformat()

            proposal_id = str(uuid.uuid4())
            digest = self._compute_digest(proposal_id, topic, solver_result.items)

            proposal = PlaylistProposal(
                proposal_id=proposal_id,
                topic=topic,
                total_duration_seconds=total_duration_seconds,
                max_video_duration_seconds=max_video_duration_seconds,
                language=language,
                items=solver_result.items,
                created_at=now_iso,
                expires_at=expires_iso,
                state=ProposalState.PROPOSED,
                digest=digest,
                privacy_status=PrivacyStatus.PRIVATE,
                quota_reservation_general=est["general"],
                quota_reservation_write=est.get("write", 0),
            )

            # FR-4.5: persist proposal BEFORE returning (no insert while PROPOSED)
            self._proposal_store.save(proposal)

            # Build output for FR-4.4
            return {
                "proposal_id": proposal_id,
                "digest": digest,
                "topic": f"[DATA] {topic}",
                "feasible": solver_result.feasible,
                "infeasible_reason": solver_result.infeasible_reason if not solver_result.feasible else "",
                "total_duration": proposal.total_duration_human(),
                "total_duration_seconds": proposal.total_actual_seconds,
                "requested_duration_seconds": total_duration_seconds,
                "video_count": len(solver_result.items),
                "items": [
                    {
                        "video_id": item.video_id,
                        "title": f"[DATA] {item.title}",
                        "channel": f"[DATA] {item.channel_title}",
                        "duration": item.duration_human(),
                        "duration_seconds": item.duration_seconds,
                        "url": item.url,
                    }
                    for item in solver_result.items
                ],
                "expires_at": expires_iso,
                "privacy_status": "private (default, FR-4.9)",
                "constraint_check": {
                    "language": language or "any",
                    "max_video_duration_seconds": max_video_duration_seconds or "none",
                    "fill_ratio_met": solver_result.feasible,
                },
                "confirmation_instructions": (
                    "To create this playlist, call create_playlist with the proposal_id "
                    f"({proposal_id!r}) and digest ({digest!r}). "
                    "This requires explicit human approval — the AI client cannot approve on your behalf."
                ),
            }
        except Exception:
            # Release reservation on failure
            self._quota.release(general=est["general"], search=est["search"])
            raise

    def _compute_digest(
        self, proposal_id: str, topic: str, items: list[PlaylistItem]
    ) -> str:
        payload = {
            "proposal_id": proposal_id,
            "topic": topic,
            "item_ids": [i.video_id for i in items],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()


class CreatePlaylistUseCase:
    """FR-4.6 to FR-4.13: create playlist after verified human confirmation.

    SAFETY: No playlist write without human-originated confirmation
    bound to proposal_id + digest + expiry + single-use (FR-4.6, ADR-A).
    """

    def __init__(
        self,
        playlist_writer: PlaylistWriter,
        quota: QuotaLedger,
        proposal_store: ProposalStore,
        audit_log: AuditLog,
        clock: Clock,
        config: Config,
    ) -> None:
        self._writer = playlist_writer
        self._quota = quota
        self._proposal_store = proposal_store
        self._audit = audit_log
        self._clock = clock
        self._cfg = config

    async def create(
        self,
        proposal_id: str,
        confirmation_digest: str,
        privacy_status: str = "private",
    ) -> dict[str, object]:
        """FR-4.6 to FR-4.13: validate approval and create playlist."""
        # Load proposal
        proposal = self._proposal_store.load(proposal_id)
        if proposal is None:
            raise proposal_not_found(proposal_id)

        # FR-4.7: reject expired
        now_ts = self._clock.utcnow_timestamp()
        import datetime
        expires_ts = datetime.datetime.fromisoformat(proposal.expires_at).timestamp()
        if now_ts > expires_ts:
            self._proposal_store.update_state(proposal_id, state=ProposalState.EXPIRED)
            self._quota.release(
                general=proposal.quota_reservation_general,
                search=0,
            )
            raise proposal_expired(proposal_id)

        # FR-4.7: reject already-used
        if proposal.state in (
            ProposalState.CREATED, ProposalState.CONFIRMED,
            ProposalState.PARTIAL, ProposalState.FAILED,
            ProposalState.CANCELLED, ProposalState.EXPIRED,
        ):
            if proposal.state != ProposalState.PROPOSED:
                raise proposal_already_used(proposal_id)

        # ADR-A: validate digest (approval must be bound to proposal content)
        if confirmation_digest != proposal.digest:
            raise approval_rejected(
                f"Digest mismatch: provided {repr(confirmation_digest[:8])}... "
                f"does not match proposal {repr(proposal.digest[:8])}..."
            )

        # Validate privacy status
        try:
            ps = PrivacyStatus(privacy_status)
        except ValueError:
            ps = PrivacyStatus.PRIVATE

        # Transition to CONFIRMED (FR-4.5: no insert while PROPOSED)
        new_state = transition(proposal_id, proposal.state, ProposalState.CONFIRMED)
        self._proposal_store.update_state(proposal_id, state=new_state, privacy_status=ps)

        # Persist operation state BEFORE each write (ADR-C)
        try:
            # Create the playlist (playlists.insert)
            playlist_id = await self._writer.create_playlist(
                title=f"[DATA] {proposal.topic}",
                description=(
                    f"[DATA] Created by Cerebra from proposal {proposal_id}. "
                    f"Topic: {proposal.topic}"
                ),
                privacy_status=ps.value,
            )
            self._quota.consume("playlists.insert", 1)
            self._proposal_store.update_state(proposal_id, playlist_id=playlist_id)

        except Exception as exc:
            self._proposal_store.update_state(proposal_id, state=ProposalState.FAILED)
            self._quota.release(general=proposal.quota_reservation_general)
            raise

        # Add items (playlistItems.insert) with per-item state tracking (ADR-C)
        failed_items: list[str] = []
        for position, item in enumerate(proposal.items):
            try:
                await self._writer.add_playlist_item(playlist_id, item.video_id, position)
                self._quota.consume("playlistItems.insert", 1)
            except Exception:
                failed_items.append(item.video_id)

        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"

        if failed_items:
            # FR-4.13: partial creation — report and allow retry
            self._proposal_store.update_state(
                proposal_id,
                state=ProposalState.PARTIAL,
                failed_item_ids=failed_items,
                playlist_url=playlist_url,
            )
            # FR-4.8: audit log
            self._audit.log_creation(proposal_id, playlist_id, self._clock.utcnow_iso())
            return {
                "status": "PARTIAL",
                "playlist_id": playlist_id,
                "playlist_url": playlist_url,
                "failed_video_ids": failed_items,
                "message": (
                    f"Playlist created but {len(failed_items)} video(s) could not be added. "
                    "You can retry adding the missing items."
                ),
            }

        # Full success
        self._proposal_store.update_state(
            proposal_id, state=ProposalState.CREATED, playlist_url=playlist_url
        )
        self._quota.release(
            general=max(0, proposal.quota_reservation_general - QUOTA_COSTS["playlists.insert"]
                        - len(proposal.items) * QUOTA_COSTS["playlistItems.insert"])
        )
        # FR-4.8: audit log (time, proposal_id, playlist_id only)
        self._audit.log_creation(proposal_id, playlist_id, self._clock.utcnow_iso())

        return {
            "status": "CREATED",
            "playlist_id": playlist_id,
            "playlist_url": playlist_url,
            "video_count": len(proposal.items),
            "total_duration": proposal.total_duration_human(),
            "privacy_status": ps.value,
        }
