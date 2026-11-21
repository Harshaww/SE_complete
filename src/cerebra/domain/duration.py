"""ISO 8601 duration parsing (SRS 3.4, FR-4.2).

YouTube API returns durations like PT1H2M3S.
"""

from __future__ import annotations

import re

_ISO8601_RE = re.compile(
    r"^P"
    r"(?:(\d+)Y)?"  # years (ignored – not used by YouTube)
    r"(?:(\d+)M)?"  # months (ignored)
    r"(?:(\d+)W)?"  # weeks
    r"(?:(\d+)D)?"  # days
    r"(?:T"
    r"(?:(\d+)H)?"  # hours
    r"(?:(\d+)M)?"  # minutes
    r"(?:(\d+(?:\.\d+)?)S)?"  # seconds (may be fractional)
    r")?$"
)


def parse_duration(iso: str) -> int:
    """Parse an ISO 8601 duration string to total seconds.

    Raises ValueError for invalid input.
    Fractional seconds are truncated to int.

    >>> parse_duration("PT1H2M3S")
    3723
    >>> parse_duration("PT30M")
    1800
    >>> parse_duration("P1DT2H")
    93600
    """
    if not iso or not iso.startswith("P"):
        raise ValueError(f"Invalid ISO 8601 duration: {iso!r}")

    m = _ISO8601_RE.match(iso.upper())
    if not m:
        raise ValueError(f"Invalid ISO 8601 duration: {iso!r}")

    _years, _months, weeks, days, hours, minutes, seconds = m.groups(default="0")
    total = (
        int(weeks or 0) * 7 * 86400
        + int(days or 0) * 86400
        + int(hours or 0) * 3600
        + int(minutes or 0) * 60
        + int(float(seconds or 0))
    )
    return total


def seconds_to_iso8601(total_seconds: int) -> str:
    """Convert integer seconds to an ISO 8601 duration string.

    >>> seconds_to_iso8601(3723)
    'PT1H2M3S'
    >>> seconds_to_iso8601(90)
    'PT1M30S'
    >>> seconds_to_iso8601(0)
    'PT0S'
    """
    if total_seconds < 0:
        raise ValueError(f"Duration cannot be negative: {total_seconds}")
    s = total_seconds
    hours, rem = divmod(s, 3600)
    minutes, secs = divmod(rem, 60)
    parts = ["P", "T"]
    if hours:
        parts.append(f"{hours}H")
    if minutes:
        parts.append(f"{minutes}M")
    if secs or total_seconds == 0:
        parts.append(f"{secs}S")
    return "".join(parts)
