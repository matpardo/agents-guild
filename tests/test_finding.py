import json

from guild import schema
from guild.cli import _build_context
from guild.commands import rebuild as rebuild_commands
from tests.testutil import GuildTestCase


class FindingTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])

    def _set_threshold(self, value):
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data["finding_guard_threshold"] = value
        config_file.write_text(json.dumps(data))

    def _record(self, number, cls="missing-audit", repo="acme/app"):
        return self.run_cli(
            ["finding", "record", "{}#{}".format(repo, number), "--class", cls], "sess-1", self.repo_dir
        )

    def _rows(self):
        conn = _build_context("sess-1", self.root).conn
        return conn.execute("SELECT * FROM findings ORDER BY number").fetchall()

    def _guard_notices(self):
        conn = _build_context("sess-1", self.root).conn
        return conn.execute("SELECT * FROM notices WHERE announces LIKE 'finding:%'").fetchall()

    def test_record_stores_finding(self):
        code, out, _ = self._record(1)
        self.assertEqual(code, 0)
        self.assertIn("1 PR(s)", out)
        row = self._rows()[0]
        self.assertEqual(
            (row["project"], row["class"], row["repo"], row["number"]), ("acme", "missing-audit", "acme/app", 1)
        )

    def test_same_pr_and_class_counts_once(self):
        self._record(1)
        _, out, _ = self._record(1)
        self.assertEqual(len(self._rows()), 1)
        self.assertIn("1 PR(s)", out)

    def test_guard_notice_is_authored_by_guild(self):
        self._set_threshold(1)
        self._record(1)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("[guild]", out)

    def test_notice_fires_once_at_threshold(self):
        self._set_threshold(2)
        self._record(1)
        self.assertEqual(self._guard_notices(), [])
        self._record(2)
        notices = self._guard_notices()
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]["scope"], "project:acme")
        self.assertEqual(
            notices[0]["text"],
            "finding class missing-audit repeated 2 times in acme: make it an architecture guard",
        )
        self._record(3)
        self.assertEqual(len(self._guard_notices()), 1)

    def test_no_config_means_no_notice(self):
        for number in (1, 2, 3):
            self._record(number)
        self.assertEqual(self._guard_notices(), [])

    def test_repo_outside_project_errors(self):
        code, _, err = self._record(1, repo="other/app")
        self.assertEqual(code, 1)
        self.assertIn("not in project", err)

    def test_invalid_slug_errors(self):
        code, _, err = self._record(1, cls="bad class")
        self.assertEqual(code, 1)
        self.assertIn("invalid finding class", err)

    def test_rebuild_reproduces_table(self):
        self._record(1)
        self._record(2, cls="mask")
        ctx = _build_context("sess-1", self.root)
        before = [dict(row) for row in self._rows()]
        rebuild_commands.run(ctx)
        self.assertEqual([dict(row) for row in self._rows()], before)
        self.assertIn("findings", schema.PROJECTION_TABLES)

    def test_threshold_validation(self):
        for bad in (0, -1, "2", True):
            self._set_threshold(bad)
            code, _, err = self._record(1)
            self.assertEqual(code, 1)
            self.assertIn("finding_guard_threshold", err)
