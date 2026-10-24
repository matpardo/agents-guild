import unittest
from datetime import datetime, timedelta, timezone

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

    def test_rejects_duration_beyond_ten_years(self):
        with self.assertRaises(GuildError):
            timeutil.parse_duration("99999999999d")
        with self.assertRaises(GuildError):
            timeutil.parse_duration("3651d")

    def test_accepts_ten_years(self):
        self.assertEqual(timeutil.parse_duration("3650d"), timedelta(days=3650))

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


class AgeLabelTests(unittest.TestCase):
    def _label(self, delta):
        now = datetime(2026, 1, 10, tzinfo=timezone.utc)
        return timeutil.age_label(now, timeutil.to_iso(now - delta))

    def test_seconds(self):
        self.assertEqual(self._label(timedelta(seconds=45)), "45s")

    def test_minutes(self):
        self.assertEqual(self._label(timedelta(minutes=12, seconds=30)), "12m")

    def test_hours(self):
        self.assertEqual(self._label(timedelta(hours=3, minutes=59)), "3h")

    def test_days(self):
        self.assertEqual(self._label(timedelta(days=2, hours=5)), "2d")

    def test_future_since_is_zero_seconds(self):
        self.assertEqual(self._label(timedelta(seconds=-5)), "0s")


if __name__ == "__main__":
    unittest.main()


class DatesLabelTests(unittest.TestCase):
    _CREATED = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)

    def _label(self, updated):
        return timeutil.dates_label(
            self._CREATED.isoformat(), None if updated is None else updated.isoformat()
        )

    def test_none_created_gives_none(self):
        self.assertIsNone(timeutil.dates_label(None, None))

    def test_same_minute_gives_created_only(self):
        expected = "created " + timeutil.issued_label(self._CREATED.isoformat())
        self.assertEqual(self._label(self._CREATED + timedelta(seconds=30)), expected)

    def test_missing_updated_gives_created_only(self):
        self.assertEqual(self._label(None), "created " + timeutil.issued_label(self._CREATED.isoformat()))

    def test_later_update_gives_both(self):
        later = self._CREATED + timedelta(minutes=2)
        expected = "created {} · updated {}".format(
            timeutil.issued_label(self._CREATED.isoformat()), timeutil.issued_label(later.isoformat())
        )
        self.assertEqual(self._label(later), expected)
