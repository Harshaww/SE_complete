"""Out-of-band local CLI (ADR-A §3, ADR-D §4-5, ADR-C §6).

    python -m cerebra.cli approve <proposal_id>     # human approval of a playlist write
    cerebra-cli login [--write]                     # OAuth (read-only, or + write scope)
    cerebra-cli logout                              # revoke + delete local token
    cerebra-cli recover <proposal_id>               # reconcile a PARTIAL write safely
    cerebra-cli pending                             # list proposals needing attention
    cerebra-cli status                              # auth / quota overview
    cerebra-cli clear-cache                         # delete cached YouTube data (NFR-PV-2)

Why ``approve`` exists: an MCP client (and the model behind it) can read every field of a
proposal, including its digest, so passing the digest back proves nothing about a *human*.
``approve`` runs in the user's own terminal, requires an interactive TTY, makes the person
re-type part of the digest, and only then records an approval that ``create_playlist``
demands. The MCP server can never write that record.

Prompts and diagnostics go to stderr; machine-readable results go to stdout.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import hmac
import json
import sys
import unicodedata
from collections.abc import Callable
from typing import Any, TextIO

from cerebra.config import get_config, load_env_file
from cerebra.domain.entities import ProposalState
from cerebra.domain.errors import CerebraError
from cerebra.infrastructure.auth.oauth_manager import SCOPE_READONLY, SCOPE_WRITE
from cerebra.infrastructure.composition import Container, build_container
from cerebra.mcp_tools.validation import validate_proposal_id

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

_CONFIRM_PREFIX_LEN = 8


def safe_terminal_text(text: str, limit: int = 120) -> str:
    """Strip control/format characters so video titles can't inject terminal escape codes."""
    cleaned = "".join(ch for ch in text if unicodedata.category(ch) not in ("Cc", "Cf"))
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


def _default_container() -> Container:
    load_env_file()  # optional untracked .env (FR-5.2); real env vars win
    cfg = get_config()
    return build_container(cfg, use_fixtures=cfg.use_fixtures)


class _Cli:
    def __init__(
        self,
        container_factory: Callable[[], Container],
        input_fn: Callable[[str], str],
        isatty: Callable[[], bool],
        out: TextIO,
        err: TextIO,
    ) -> None:
        self._factory = container_factory
        self._input = input_fn
        self._isatty = isatty
        self._out = out
        self._err = err

    def _say(self, msg: str = "") -> None:
        print(msg, file=self._err)

    def _emit(self, obj: Any) -> None:
        print(json.dumps(obj, indent=2, default=str), file=self._out)

    # ── approve ──────────────────────────────────────────────────────────────

    def approve(self, proposal_id_raw: str) -> int:
        if not self._isatty():
            self._say(
                "Refusing to approve: this command needs an interactive terminal so a human "
                "can review the proposal. It cannot be run from a script or by an AI client."
            )
            return EXIT_USAGE
        proposal_id = validate_proposal_id(proposal_id_raw)
        c = self._factory()
        assert c.proposal_store is not None and c.approvals is not None and c.clock is not None
        proposal = c.proposal_store.load(proposal_id)
        if proposal is None:
            self._say(f"No proposal {proposal_id}. Run propose_playlist again.")
            return EXIT_FAIL
        if proposal.state != ProposalState.PROPOSED:
            self._say(
                f"Proposal is {proposal.state.value}; only PROPOSED proposals can be approved."
            )
            return EXIT_FAIL
        expires = datetime.datetime.fromisoformat(proposal.expires_at).timestamp()
        if c.clock.utcnow_timestamp() > expires:
            self._say("This proposal has expired (15-minute limit). Run propose_playlist again.")
            return EXIT_FAIL

        self._say("")
        self._say("═══ Cerebra: approve YouTube playlist creation ═══")
        self._say(f"Proposal : {proposal.proposal_id}")
        self._say(f"Topic    : {safe_terminal_text(proposal.topic)}")
        self._say(f"Privacy  : {proposal.privacy_status.value}")
        self._say(f"Videos   : {len(proposal.items)}  ({proposal.total_duration_human()})")
        for n, item in enumerate(proposal.items, 1):
            self._say(
                f"  {n:>2}. {safe_terminal_text(item.title, 70)}  "
                f"[{item.duration_human()}]  {item.video_id}"
            )
        self._say(f"Expires  : {proposal.expires_at}")
        self._say("")
        self._say("Approving lets Cerebra create ONE new playlist in your YouTube account.")
        self._say("It will not edit or delete anything that already exists.")
        expected = proposal.digest[:_CONFIRM_PREFIX_LEN]
        typed = self._input(
            f"To approve, type the first {_CONFIRM_PREFIX_LEN} characters of the digest "
            f"({expected}), or press Enter to cancel: "
        ).strip()
        if not typed or not hmac.compare_digest(typed.lower().encode(), expected.encode()):
            self._say("Not approved. Nothing was recorded.")
            return EXIT_FAIL
        c.approvals.record(
            proposal.proposal_id, proposal.digest, proposal.account_id, c.clock.utcnow_iso()
        )
        self._say("Approved. Now ask your assistant to call create_playlist with:")
        self._say(f"  proposal_id         = {proposal.proposal_id}")
        self._say(f"  confirmation_digest = {proposal.digest}")
        self._emit({"approved": True, "proposal_id": proposal.proposal_id})
        return EXIT_OK

    # ── auth ─────────────────────────────────────────────────────────────────

    def login(self, write: bool) -> int:
        c = self._factory()
        if c.oauth is None:
            self._say("Fixture mode is active (CEREBRA_USE_FIXTURES): no OAuth login needed.")
            return EXIT_USAGE
        scopes = [SCOPE_READONLY, SCOPE_WRITE] if write else [SCOPE_READONLY]
        if write:
            self._say("Requesting WRITE access (scope: youtube) so Cerebra can create playlists.")
        self._emit(c.oauth.login(scopes))
        return EXIT_OK

    def logout(self) -> int:
        c = self._factory()
        if c.oauth is None:
            self._say("Fixture mode is active: no token to revoke.")
            return EXIT_USAGE
        self._emit(c.oauth.revoke())
        return EXIT_OK

    # ── recovery / status ────────────────────────────────────────────────────

    def recover(self, proposal_id_raw: str) -> int:
        proposal_id = validate_proposal_id(proposal_id_raw)
        c = self._factory()
        assert c.recover is not None
        self._emit(asyncio.run(c.recover.recover(proposal_id)))
        return EXIT_OK

    def pending(self) -> int:
        c = self._factory()
        assert c.recover is not None
        self._emit(
            [
                {
                    "proposal_id": p.proposal_id,
                    "state": p.state.value,
                    "playlist_id": p.playlist_id,
                    "ambiguous": p.ambiguous,
                    "missing_items": [
                        i.video_id for i in p.items if p.item_states.get(i.video_id) != "INSERTED"
                    ],
                }
                for p in c.recover.pending()
            ]
        )
        return EXIT_OK

    def clear_cache(self) -> int:
        """NFR-PV-2: delete every cached API response (likes, subscriptions, search results)."""
        c = self._factory()
        assert c.cache is not None
        c.cache.clear_all()
        self._emit({"cache_cleared": True})
        return EXIT_OK

    def status(self) -> int:
        c = self._factory()
        out: dict[str, Any] = {"mode": "live" if c.live else "fixtures", "quota": c.quota.status()}
        if c.oauth is not None:
            out["auth"] = c.oauth.status()
        self._emit(out)
        return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="cerebra-cli", description="Cerebra local administration")
    sub = ap.add_subparsers(dest="command", required=True)
    a = sub.add_parser("approve", help="human approval of a playlist proposal (interactive)")
    a.add_argument("proposal_id")
    lg = sub.add_parser("login", help="authorise with Google (read-only by default)")
    lg.add_argument("--write", action="store_true", help="also request playlist-write access")
    sub.add_parser("logout", help="revoke access and delete the local token")
    r = sub.add_parser("recover", help="safely finish an interrupted playlist write")
    r.add_argument("proposal_id")
    sub.add_parser("pending", help="list proposals that need recovery")
    sub.add_parser("clear-cache", help="delete all locally cached YouTube data (NFR-PV-2)")
    sub.add_parser("status", help="show auth and quota status")
    return ap


def main(
    argv: list[str] | None = None,
    *,
    container_factory: Callable[[], Container] | None = None,
    input_fn: Callable[[str], str] = input,
    isatty: Callable[[], bool] | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    tty = isatty or (lambda: sys.stdin.isatty() and sys.stderr.isatty())
    cli = _Cli(
        container_factory or _default_container, input_fn, tty, out or sys.stdout, err or sys.stderr
    )
    try:
        if args.command == "approve":
            return cli.approve(args.proposal_id)
        if args.command == "login":
            return cli.login(args.write)
        if args.command == "logout":
            return cli.logout()
        if args.command == "recover":
            return cli.recover(args.proposal_id)
        if args.command == "pending":
            return cli.pending()
        if args.command == "clear-cache":
            return cli.clear_cache()
        return cli.status()
    except CerebraError as exc:
        print(f"error [{exc.code.value}]: {exc.message}", file=err or sys.stderr)
        if exc.suggested_action:
            print(f"  → {exc.suggested_action}", file=err or sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
