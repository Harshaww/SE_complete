"""redact_results.py - strip secrets and personal identifiers from JUnit XML (NFR-SE-2, NFR-PV-1).

Usage:  python scripts/redact_results.py live-results.xml [more.xml ...]

Used by the live-API workflows before results are uploaded. Files are rewritten IN PLACE.
Redacts (a) the literal values of secret environment variables and (b) well-known token
shapes (Google access/refresh tokens, API keys, client secrets, bearer headers, JWTs),
e-mail addresses and channel IDs. Exit code 0 on success, 1 if a file is missing or unreadable.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REDACTED = "[REDACTED]"

# Environment variables whose VALUES must never appear in an uploaded artifact.
SECRET_ENV_VARS = (
    "CEREBRA_REFRESH_TOKEN",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_CLIENT_ID",
    "CEREBRA_YOUTUBE_API_KEY",
)

PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ya29\.[0-9A-Za-z_\-]+"),  # Google OAuth access token
    re.compile(r"1//[0-9A-Za-z_\-]{20,}"),  # Google OAuth refresh token
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),  # Google API key
    re.compile(r"GOCSPX-[0-9A-Za-z_\-]{10,}"),  # Google OAuth client secret
    re.compile(r"[0-9]+-[0-9a-z]{20,}\.apps\.googleusercontent\.com"),  # OAuth client id
    re.compile(r"(?i)\bBearer\s+[0-9A-Za-z._\-]{10,}"),
    re.compile(r"\beyJ[0-9A-Za-z_\-]{8,}\.[0-9A-Za-z_\-]{8,}\.[0-9A-Za-z_\-]{8,}"),  # JWT
    re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+"),  # e-mail address
    re.compile(r"\bUC[0-9A-Za-z_\-]{22}\b"),  # channel ID (account identifier)
)


def _secret_values(env: dict[str, str] | None = None) -> list[str]:
    source = os.environ if env is None else env
    values = [source.get(name, "") for name in SECRET_ENV_VARS]
    # Longest first so a value that contains another is replaced whole.
    return sorted({v for v in values if len(v) >= 6}, key=len, reverse=True)


def redact_text(text: str, env: dict[str, str] | None = None) -> str:
    for value in _secret_values(env):
        text = text.replace(value, REDACTED)
    for pattern in PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def redact_file(path: Path, env: dict[str, str] | None = None) -> int:
    """Rewrite ``path`` in place; return the number of redactions made."""
    original = path.read_text(encoding="utf-8")
    cleaned = redact_text(original, env)
    path.write_text(cleaned, encoding="utf-8")
    return cleaned.count(REDACTED) - original.count(REDACTED)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: redact_results.py FILE [FILE ...]", file=sys.stderr)
        return 1
    status = 0
    for name in args:
        path = Path(name)
        try:
            count = redact_file(path)
        except (OSError, UnicodeDecodeError) as exc:
            print(f"redact_results: cannot process {name}: {exc}", file=sys.stderr)
            status = 1
            continue
        print(f"redact_results: {name}: {count} redaction(s)")
    return status


if __name__ == "__main__":
    sys.exit(main())
