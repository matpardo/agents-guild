import re
from pathlib import Path

from guild import pii
from tests.testutil import GuildTestCase

_TRACE_RE = re.compile(r"guild|ask #[0-9]|notice #[0-9]|idea #[0-9]|adventurer [0-9]", re.IGNORECASE)
_REPO_ROOT = Path(__file__).resolve().parents[1]


class PublishableTextTests(GuildTestCase):
    def setUp(self):
        super().setUp()
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
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )

    def test_pr_track_and_set_output_has_no_traces(self):
        code, track_out, err = self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        code, set_out, err = self.run_cli(["pr", "set", "acme/app#1", "--lifecycle", "ready"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIsNone(_TRACE_RE.search(track_out))
        self.assertIsNone(_TRACE_RE.search(set_out))

    def test_adventurer_pr_track_output_has_no_traces(self):
        self.run_cli(
            ["quest", "add", "chore", "--open", "--no-epic", "--title", "chore", "--tasks", "T01", "--titles", "one"],
            None,
            self.repo_dir,
        )
        self.run_cli(
            ["adventurer", "start", "fix typo", "--task", "chore/T01", "--reason", "test reason"],
            "adv-1",
            self.repo_dir,
        )
        code, track_out, err = self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "chore/T01", "--card", "ABC-1", "--what", "x", "--waits", "y"],
            "adv-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        self.assertIsNone(_TRACE_RE.search(track_out))

    def test_pending_reports_are_rejected_when_they_carry_a_secret_or_email(self):
        self.run_cli(
            ["quest", "add", "chore", "--open", "--no-epic", "--title", "chore", "--tasks", "T01", "--titles", "one"],
            None,
            self.repo_dir,
        )
        self.run_cli(
            ["adventurer", "start", "fix typo", "--task", "chore/T01", "--reason", "test reason"],
            "adv-1",
            self.repo_dir,
        )
        for pending in ("mail me@x.com", " "):
            code, out, err = self.run_cli(["adventurer", "done", "--pending", pending], "adv-1", self.repo_dir)
            self.assertEqual(code, 1, pending)
        code, out, err = self.run_cli(["party", "close", "alpha", "--pending", "mail me@x.com"], None, None)
        self.assertEqual(code, 1)

    def test_quest_done_output_has_no_traces(self):
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        self.run_cli(["task", "done", "demo/T01"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["quest", "done", "demo"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIsNone(_TRACE_RE.search(out))

    def test_reminder_text_states_the_rule(self):
        self.assertIn("decisión del dev", pii.LOCAL_ONLY_REMINDER)
        self.assertIn("ask #N", pii.LOCAL_ONLY_REMINDER)
        self.assertIn("optional", pii.LOCAL_ONLY_REMINDER)

    def test_ask_creation_reminds_local_only(self):
        code, out, err = self.run_cli(
            ["ask", "q?", "--context", "c", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        self.assertIn(pii.LOCAL_ONLY_REMINDER, out)

    def test_brief_states_rule_when_unbound(self):
        code, out, err = self.run_cli(["brief"], "sess-unbound", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn(pii.LOCAL_ONLY_REMINDER, out)

    def test_brief_states_rule_when_bound(self):
        code, out, err = self.run_cli(["brief"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn(pii.LOCAL_ONLY_REMINDER, out)

    def test_rules_file_states_rule(self):
        text = (_REPO_ROOT / "GUILD.md").read_text()
        self.assertIn("decisión del dev", text)
        self.assertIn("optional", text)
