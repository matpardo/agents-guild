import json
import os
import time
from datetime import datetime, timezone
from unittest import mock

from guild import ask_detail, context, db, paths
from tests.testutil import GuildTestCase

_CREATED = datetime(2026, 10, 4, 9, 15, tzinfo=timezone.utc)
_ANSWERED = datetime(2026, 10, 4, 14, 30, tzinfo=timezone.utc)


class AskLocalTimeTests(GuildTestCase):
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
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        with mock.patch("guild.timeutil.utcnow", return_value=_CREATED):
            self.run_cli(["ask", "Ship it?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir)
        with mock.patch("guild.timeutil.utcnow", return_value=_ANSWERED):
            self.run_cli(["answer", "1", "yes"], None, None)

    def test_detail_view_shows_local_times(self):
        code, out, err = self.run_cli(["asks", "1"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("· created 2026-10-04 09:15", out)
        self.assertIn("  answered: 2026-10-04 14:30", out)
        self.assertNotIn("+00:00", out)

    def test_all_listing_shows_local_answer_time(self):
        code, out, err = self.run_cli(["asks", "--all"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("     created 2026-10-04 09:15 · updated 2026-10-04 14:30", out)
        self.assertNotIn("answered:", out)
        self.assertNotIn("+00:00", out)

    def test_web_model_carries_local_labels(self):
        conn = db.connect(paths.db_path())
        ctx = context.RunContext(
            conn,
            None,
            None,
            _ANSWERED,
            None,
            paths.claude_sessions_dir(),
            paths.projects_config_dir(),
            None,
        )
        row = conn.execute("SELECT * FROM asks WHERE id = 1").fetchone()
        model = json.loads(json.dumps(ask_detail.build(ctx, row)))
        conn.close()
        self.assertEqual(model["created"], "2026-10-04 09:15")
        self.assertEqual(model["answered"], "2026-10-04 14:30")
