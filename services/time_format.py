"""Convert standardized absolute dates to Discord timestamps."""

from __future__ import annotations

import re
from datetime import datetime, timezone


_DISCORD_TIMESTAMP = re.compile(r"<t:-?\d+(?::[tTdDfFR])?>")
_ABSOLUTE = re.compile(
    r"\b(?:"
    r"\d{4}-\d{1,2}-\d{1,2}(?:[T ]\d{1,2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?"
    r"|\d{1,2}/\d{1,2}/\d{4}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?"
    r"|\d{1,2}-\d{1,2}-\d{4}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?"
    r"|\d{4}/\d{1,2}/\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?"
    r"|\d{1,2}\.\d{1,2}\.\d{4}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?"
    r")\b",
    re.IGNORECASE,
)


def _discord_timestamp(value: datetime, style: str) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return f"<t:{int(value.timestamp())}:{style}>"


def _parse_absolute(value: str) -> tuple[datetime, str] | None:
    text = value.strip().replace("Z", "+00:00")
    formats = (
        ("%Y-%m-%dT%H:%M:%S%z", "F"), ("%Y-%m-%dT%H:%M%z", "F"),
        ("%Y-%m-%d %H:%M:%S%z", "F"), ("%Y-%m-%d %H:%M%z", "F"),
        ("%Y-%m-%d %H:%M:%S", "F"), ("%Y-%m-%d %H:%M", "F"),
        ("%Y-%m-%d", "D"), ("%d/%m/%Y %H:%M:%S", "F"),
        ("%d/%m/%Y %H:%M", "F"), ("%d/%m/%Y", "D"),
        ("%d-%m-%Y %H:%M:%S", "F"), ("%d-%m-%Y %H:%M", "F"),
        ("%d-%m-%Y", "D"),
        ("%Y/%m/%d %H:%M:%S", "F"), ("%Y/%m/%d %H:%M", "F"),
        ("%Y/%m/%d", "D"), ("%d.%m.%Y %H:%M:%S", "F"),
        ("%d.%m.%Y %H:%M", "F"), ("%d.%m.%Y", "D"),
    )
    for fmt, style in formats:
        try:
            return datetime.strptime(text, fmt), style
        except ValueError:
            continue
    return None


def format_time_expressions(text: str, *, now: datetime | None = None) -> str:
    """Replace standardized absolute date expressions with Discord timestamps.

    Existing Discord timestamps and natural-language expressions are left untouched.
    Dates use ``D`` and date-times use ``F``.
    """
    if not text:
        return text
    now = now or datetime.now(timezone.utc)

    def absolute(match: re.Match[str]) -> str:
        parsed = _parse_absolute(match.group(0))
        return _discord_timestamp(*parsed) if parsed else match.group(0)

    return _ABSOLUTE.sub(absolute, text)
