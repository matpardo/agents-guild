import unittest
from datetime import datetime, timezone

from guild.errors import GuildError
from guild import timeutil


class DurationParsingTests(unittest.TestCase):
    def test_parses_minutes(self):
        delta = timeutil.parse_duration("30m")
        self.assertEqual(delta.total_seconds(), 1800)

    def test_parses_hours(self):
        delta = timeutil.parse_duration("8h")
        self.assertEqual(delta.total_seconds(), 8 * 3600)

    def test_parses_days(self):
        delta = timeutil.parse_duration("3d")
        self.assertEqual(delta.total_seconds(), 3 * 86400)

    def test_rejects_bad_format(self):
        with self.assertRaises(GuildError):
            timeutil.parse_duration("30 minutes")

    def test_rejects_unit_missing(self):
        with self.assertRaises(GuildError):
            timeutil.parse_duration("30")


class ExpiryTests(unittest.TestCase):
    def test_expires_at_iso_adds_duration(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = timeutil.expires_at_iso(now, "1h")
        self.assertEqual(result, "2026-01-01T01:00:00+00:00")

    def test_is_expired_true_when_past(self):
        now = datetime(2026, 1, 1, 2, tzinfo=timezone.utc)
        self.assertTrue(timeutil.is_expired(now, "2026-01-01T01:00:00+00:00"))

    def test_is_expired_false_when_future(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertFalse(timeutil.is_expired(now, "2026-01-01T01:00:00+00:00"))


if __name__ == "__main__":
    unittest.main()
