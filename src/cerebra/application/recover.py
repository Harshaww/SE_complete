"""Recovery of partially-written playlists (ADR-C §3, FR-4.13).

Never blind-retries a write. For a proposal left in PARTIAL (or stuck in CONFIRMED after a
crash) it first READS remote state:

  1. playlist_id unknown  → look for a playlist whose description carries this proposal_id
                            (written by CreatePlaylistUseCase). Found → adopt it.
                            Not found → only then is ``playlists.insert`` safe to repeat.
  2. playlist_id known    → list its items; anything already there is marked INSERTED.
  3. Only the still-missing items are inserted, once each.

The proposal was already human-approved and consumed; recovery can only finish THAT approved
item set — it never adds anything new, and never edits or deletes (NFR-SA-2).
"""
from __future__ import annotations

from cerebra.application.playlist import AccountIdProvider
from cerebra.config import Config
from cerebra.domain.entities import PlaylistItem, PlaylistProposal, ProposalState
from cerebra.domain.errors import (
    CerebraError,
    ErrorCode,
    approval_rejected,
    proposal_not_found,
    quota_budget_exceeded,
)
from cerebra.domain.quota import QUOTA_COSTS, QuotaLedger
from cerebra.domain.state_machine import transition
from cerebra.ports.interfaces import (
    AuditLog,
    Clock,
    PlaylistWriter,
    ProposalStore,
    UserLibraryReader,
)

_RECOVERABLE = (ProposalState.PARTIAL, ProposalState.CONFIRMED)


class RecoverPlaylistUseCase:
    def __init__(
        self,
        playlist_writer: PlaylistWriter,
        user_library: UserLibraryReader,
        quota: QuotaLedger,
        proposal_store: ProposalStore,
        audit_log: AuditLog,
        clock: Clock,
        config: Config,
        account_id_provider: AccountIdProvider | None = None,
    ) -> None:
        self._writer = playlist_writer
        self._library = user_library
        self._quota = quota
        self._store = proposal_store
        self._audit = audit_log
        self._clock = clock
        self._cfg = config
        self._account_provider = account_id_provider

    def pending(self) -> list[PlaylistProposal]:
        """Proposals needing reconciliation (PARTIAL, or CONFIRMED after a crash)."""
        return [p for p in self._store.list_active() if p.state in _RECOVERABLE]

    async def recover(self, proposal_id: str) -> dict[str, object]:
        proposal = self._store.load(proposal_id)
        if proposal is None:
            raise proposal_not_found(proposal_id)
        if proposal.state not in _RECOVERABLE:
            return {
                "status": proposal.state.value,
                "playlist_id": proposal.playlist_id,
                "message": f"Nothing to recover: proposal is {proposal.state.value}.",
            }
        if self._account_provider is not None:
            current = await self._account_provider()
            if current != proposal.account_id:
                raise approval_rejected("proposal belongs to a different YouTube account")

        # FR-5.8: the reconciliation itself costs quota (reads + at most one insert per item)
        remaining_items = [
            i for i in proposal.items if proposal.item_states.get(i.video_id) != "INSERTED"
        ]
        needed = 2 + len(remaining_items) * QUOTA_COSTS["playlistItems.insert"] \
            + (QUOTA_COSTS["playlists.insert"] if not proposal.playlist_id else 0)
        if not self._quota.can_afford(general=needed):
            raise quota_budget_exceeded(needed, self._quota.general_remaining)

        await self._writer.ensure_write_access()

        if proposal.state == ProposalState.CONFIRMED:  # crashed before PARTIAL was persisted
            self._store.update_state(
                proposal_id, state=transition(proposal_id, proposal.state, ProposalState.PARTIAL)
            )

        playlist_id = proposal.playlist_id
        notes: list[str] = []

        # 1. Find (or, only if truly absent, create) the playlist
        if not playlist_id:
            playlist_id = await self._find_remote_playlist(proposal_id)
            if playlist_id:
                notes.append(
                    "found existing playlist on YouTube; adopted it (no duplicate created)"
                )
                self._audit.log_event(proposal_id, playlist_id, "recovered:playlist_found",
                                      self._clock.utcnow_iso())
            else:
                playlist_id = await self._writer.create_playlist(
                    title=proposal.topic,
                    description=(
                        f"Created by Cerebra from proposal {proposal_id}. "
                        f"Topic: {proposal.topic}"
                    ),
                    privacy_status=proposal.privacy_status.value,
                )
                self._quota.consume("playlists.insert", 1)
                notes.append("playlist was not on YouTube; created it once")
                self._audit.log_event(proposal_id, playlist_id, "recovered:playlist_created",
                                      self._clock.utcnow_iso())
            self._store.update_state(proposal_id, playlist_id=playlist_id)

        # 2. Read remote items; adopt whatever is already there
        remote = await self._library.get_playlist_items(playlist_id, max_results=500)
        remote_ids = {v.video_id for v in remote}
        item_states = dict(proposal.item_states)
        for item in proposal.items:
            if item.video_id in remote_ids:
                item_states[item.video_id] = "INSERTED"
            elif item_states.get(item.video_id) == "INSERTED":
                item_states[item.video_id] = "PENDING"   # claimed but not actually there
        self._store.update_state(proposal_id, item_states=dict(item_states))

        # 3. Insert only what is missing, once each, appended in order
        missing: list[PlaylistItem] = [
            i for i in proposal.items if item_states.get(i.video_id) != "INSERTED"
        ]
        position = len(remote_ids)
        for item in missing:
            item_states[item.video_id] = "PENDING"
            self._store.update_state(proposal_id, item_states=dict(item_states))
            try:
                await self._writer.add_playlist_item(playlist_id, item.video_id, position)
            except Exception as exc:
                item_states[item.video_id] = "FAILED"
                self._store.update_state(proposal_id, item_states=dict(item_states))
                self._audit.log_event(
                    proposal_id, playlist_id, f"recover_failed:{item.video_id}",
                    self._clock.utcnow_iso(),
                )
                if isinstance(exc, CerebraError) and exc.code in (
                    ErrorCode.QUOTA_EXHAUSTED, ErrorCode.QUOTA_BUDGET_EXCEEDED,
                    ErrorCode.AUTH_REQUIRED, ErrorCode.AUTH_EXPIRED,
                    ErrorCode.INSUFFICIENT_SCOPE,
                ):
                    break
                continue
            self._quota.consume("playlistItems.insert", 1)
            item_states[item.video_id] = "INSERTED"
            self._store.update_state(proposal_id, item_states=dict(item_states))
            position += 1

        failed = [i.video_id for i in proposal.items if item_states.get(i.video_id) != "INSERTED"]
        url = f"https://www.youtube.com/playlist?list={playlist_id}"
        if failed:
            self._store.update_state(
                proposal_id, failed_item_ids=failed, playlist_url=url
            )
            return {
                "status": "PARTIAL", "playlist_id": playlist_id, "playlist_url": url,
                "failed_video_ids": failed, "notes": notes,
                "message": "Some items are still missing; run recover again later.",
            }
        self._store.update_state(
            proposal_id, state=ProposalState.CREATED, failed_item_ids=[],
            playlist_url=url, ambiguous=False,
        )
        self._audit.log_event(proposal_id, playlist_id, "recovered:created",
                              self._clock.utcnow_iso())
        return {
            "status": "CREATED", "playlist_id": playlist_id, "playlist_url": url,
            "video_count": len(proposal.items), "notes": notes,
        }

    async def _find_remote_playlist(self, proposal_id: str) -> str | None:
        for pl in await self._library.get_playlists(max_results=200):
            if proposal_id in str(pl.get("description", "")):
                return str(pl.get("id", "")) or None
        return None
