import os
import time
from datetime import datetime, timezone
from unittest import mock

from guild import context, db, paths, timeutil
from guild.commands import board as board_commands
from tests.testutil import GuildTestCase

_OLDER = datetime(2026, 10, 4, 9, 15, tzinfo=timezone.utc)
_NEWER = datetime(2026, 10, 4, 14, 30, tzinfo=timezone.utc)
_READ_AT = datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc)


class NoticeIssuedTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        os.environ["TZ"] = "UTC"
        time.tzset()
        self.addCleanup(time.tzset)
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(
            ["party", "start", "beta", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-2",
            self.repo_dir,
        )
        self._create_at(_OLDER, "older notice")
        self._create_at(_NEWER, "newer notice")

    def _create_at(self, moment, text):
        with mock.patch("guild.timeutil.utcnow", return_value=moment):
            code, out, err = self.run_cli(
                ["notice", "create", text, "--to", "guild", "--ttl", "1d"], "sess-1", self.repo_dir
            )
        self.assertEqual(code, 0, err)

    def _run_at_read_time(self, argv, session_id):
        with mock.patch("guild.timeutil.utcnow", return_value=_READ_AT):
            return self.run_cli(argv, session_id, self.repo_dir)

    def test_list_shows_issue_time_newest_first(self):
        code, out, err = self._run_at_read_time(["notices"], None)
        self.assertEqual(code, 0, err)
        self.assertIn("2026-10-04 14:30", out)
        self.assertIn("2026-10-04 09:15", out)
        self.assertLess(out.index("newer notice"), out.index("older notice"))

    def test_board_shows_issue_time_newest_first(self):
        code, out, err = self._run_at_read_time(["board"], None)
        self.assertEqual(code, 0, err)
        self.assertIn("2026-10-04 14:30", out)
        self.assertLess(out.index("newer notice"), out.index("older notice"))

    def test_inbox_line_carries_issue_time(self):
        code, out, err = self._run_at_read_time(["inbox", "--since-last"], "sess-2")
        self.assertEqual(code, 0, err)
        self.assertIn('- notice #2 from alpha at 2026-10-04 14:30: "newer notice"', out)

    def test_brief_lists_notices_newest_first_with_time(self):
        code, out, err = self._run_at_read_time(["brief"], "sess-2")
        self.assertEqual(code, 0, err)
        self.assertIn("at 2026-10-04 09:15", out)
        self.assertLess(out.index("newer notice"), out.index("older notice"))

    def test_web_model_carries_issue_time_newest_first(self):
        conn = db.connect(paths.db_path())
        ctx = context.RunContext(
            conn,
            None,
            None,
            _READ_AT,
            None,
            paths.claude_sessions_dir(),
            paths.projects_config_dir(),
            None,
        )
        model = board_commands.board_model(ctx)
        conn.close()
        notices = model["notices"]
        self.assertEqual([notice["text"] for notice in notices], ["newer notice", "older notice"])
        self.assertEqual(notices[0]["issued_at"], timeutil.to_iso(_NEWER))
        self.assertEqual(notices[0]["issued"], "2026-10-04 14:30")
