from datetime import datetime, timezone

from services.time_format import format_time_expressions


NOW = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)


def test_formats_iso_date_and_datetime():
    result = format_time_expressions("2025-02-03 et 2025-02-03 14:30", now=NOW)
    assert result == "<t:1738540800:D> et <t:1738593000:F>"


def test_formats_european_date_but_preserves_relative_duration():
    result = format_time_expressions("31/12/2025, dans 2 heures", now=NOW)
    assert result == "<t:1767139200:D>, dans 2 heures"


def test_preserves_relative_duration_and_discord_timestamp():
    result = format_time_expressions("il y a 10 minutes <t:1736942400:F>", now=NOW)
    assert result == "il y a 10 minutes <t:1736942400:F>"


def test_invalid_dates_are_unchanged():
    assert format_time_expressions("2025-99-99 31/02/2025", now=NOW) == "2025-99-99 31/02/2025"


def test_preserves_common_day_words():
    assert format_time_expressions("demain / yesterday", now=NOW) == "demain / yesterday"


def test_preserves_memory_error_with_extreme_relative_value():
    message = (
        "Replacement would put memory at 2,428/2,200 chars; "
        "current_entries: 999999999999999999999999999 days"
    )

    assert format_time_expressions(message, now=NOW) == message
