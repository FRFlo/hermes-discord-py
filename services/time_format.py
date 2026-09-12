"""Convert common human-readable dates and durations to Discord timestamps."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


_DISCORD_TIMESTAMP = re.compile(r"<t:-?\d+(?::[tTdDfFR])?>")
_DAY_WORD = re.compile(r"\b(?:today|tomorrow|yesterday|aujourd'hui|demain|hier)\b", re.IGNORECASE)
_RELATIVE = re.compile(
    r"(?P<prefix>\b(?:dans|in)\s+|\b(?:il y a|ago)\s+)?"
    r"(?P<amount>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>second(?:e?s)?|sec|s|minute?s?|min|m|heure?s?|hour?s?|h|"
    r"jour?s?|day?s?|j|d|semaine?s?|week?s?|w)\b(?P<suffix>\s+ago\b)?",
    re.IGNORECASE,
)

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
    """Replace common absolute/relative time expressions with Discord timestamps.

    Existing Discord timestamps are left untouched. Relative expressions are rendered
    with ``R``; dates use ``D`` and date-times use ``F``.
    """
    if not text:
        return text
    now = now or datetime.now(timezone.utc)

    def relative(match: re.Match[str]) -> str:
        amount = float(match.group("amount").replace(",", "."))
        unit = match.group("unit").lower()
        if unit.startswith(("s", "sec")):
            delta = timedelta(seconds=amount)
        elif unit.startswith(("m", "min")):
            delta = timedelta(minutes=amount)
        elif unit.startswith(("h", "heure", "hour")):
            delta = timedelta(hours=amount)
        elif unit.startswith(("j", "d", "jour", "day")):
            delta = timedelta(days=amount)
        else:
            delta = timedelta(weeks=amount)
        prefix = (match.group("prefix") or "").lower()
        if "ago" in prefix or "ago" in (match.group("suffix") or "") or "y a" in prefix:
            delta = -delta
        return _discord_timestamp(now + delta, "R")

    # Relative first so dates inside a sentence don't interfere with absolute parsing.
    result = _RELATIVE.sub(relative, text)

    def day_word(match: re.Match[str]) -> str:
        word = match.group(0).lower()
        offset = 1 if word in {"tomorrow", "demain"} else -1 if word in {"yesterday", "hier"} else 0
        return _discord_timestamp(now + timedelta(days=offset), "D")

    result = _DAY_WORD.sub(day_word, result)

    def absolute(match: re.Match[str]) -> str:
        parsed = _parse_absolute(match.group(0))
        return _discord_timestamp(*parsed) if parsed else match.group(0)

    return _ABSOLUTE.sub(absolute, result)
