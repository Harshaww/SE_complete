"""Unit tests for domain/duration.py (FR-4.2, ISO 8601 parsing)."""

import pytest

from cerebra.domain.duration import parse_duration, seconds_to_iso8601


# mark: FR-4.2, TR-1, TR-4
class TestParseDuration:
    def test_full_hms(self):
        assert parse_duration("PT1H2M3S") == 3723

    def test_minutes_only(self):
        assert parse_duration("PT30M") == 1800

    def test_seconds_only(self):
        assert parse_duration("PT45S") == 45

    def test_hours_only(self):
        assert parse_duration("PT2H") == 7200

    def test_days_and_time(self):
        assert parse_duration("P1DT2H") == 86400 + 7200

    def test_zero_duration(self):
        assert parse_duration("PT0S") == 0

    def test_fractional_seconds_truncated(self):
        assert parse_duration("PT1.9S") == 1

    def test_uppercase_required_or_flexible(self):
        # Should parse PT1H case-insensitively
        assert parse_duration("PT1H") == 3600

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_duration("")

    def test_no_P_prefix_raises(self):
        with pytest.raises(ValueError):
            parse_duration("T1H2M3S")

    def test_weeks(self):
        assert parse_duration("P1W") == 7 * 86400


# mark: FR-4.2
class TestSecondsToIso8601:
    def test_full_hms(self):
        assert seconds_to_iso8601(3723) == "PT1H2M3S"

    def test_minutes_seconds(self):
        assert seconds_to_iso8601(90) == "PT1M30S"

    def test_zero(self):
        assert seconds_to_iso8601(0) == "PT0S"

    def test_hours_only(self):
        assert seconds_to_iso8601(7200) == "PT2H"

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            seconds_to_iso8601(-1)

    def test_round_trip(self):
        for seconds in [0, 1, 59, 60, 61, 3599, 3600, 3661, 86400]:
            iso = seconds_to_iso8601(seconds)
            assert parse_duration(iso) == seconds, f"Round-trip failed for {seconds}"
