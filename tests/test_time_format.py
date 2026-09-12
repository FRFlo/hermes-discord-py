from datetime import datetime, timezone

from services.time_format import format_time_expressions


NOW = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)


def test_formats_iso_date_and_datetime():
    result = format_time_expressions("2025-02-03 et 2025-02-03 14:30", now=NOW)
    assert result == "<t:1738540800:D> et <t:1738593000:F>"


def test_formats_european_date_and_relative_duration():
    result = format_time_expressions("31/12/2025, dans 2 heures", now=NOW)
    assert result == "<t:1767139200:D>, <t:1736949600:R>"


def test_formats_past_relative_duration_and_preserves_discord_timestamp():
    result = format_time_expressions("il y a 10 minutes <t:1736942400:F>", now=NOW)
    assert result == "<t:1736941800:R> <t:1736942400:F>"


def test_invalid_dates_are_unchanged():
    assert format_time_expressions("2025-99-99 31/02/2025", now=NOW) == "2025-99-99 31/02/2025"


def test_formats_common_day_words():
    assert format_time_expressions("demain / yesterday", now=NOW) == "<t:1737028800:D> / <t:1736856000:D>"
