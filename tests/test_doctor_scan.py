import json
import os
from unittest import mock

from tests.test_doctor import _ALL_HOOKS, _ALLOW_RULES, _ASK_RULES
from tests.testutil import GuildTestCase


class DoctorScanPrsTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.root / "home"
        (self.home / ".claude").mkdir(parents=True)
        (self.home / ".claude" / "settings.json").write_text(
            json.dumps({"hooks": _ALL_HOOKS, "permissions": {"ask": _ASK_RULES, "allow": _ALLOW_RULES}})
        )
        (self.home / ".claude" / "GUILD.md").write_text("rules")
        self.env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.register_project("acme", ["acme/app"])

    def _open_pr(self, number, title, body, comments, commits):
        return {
            "number": number,
            "title": title,
            "body": body,
            "comments": [{"body": text} for text in comments],
            "commits": [{"messageHeadline": text, "messageBody": ""} for text in commits],
        }

    def test_scan_reports_each_place_without_printing_text(self):
        self.write_gh_fixture(
            "open_acme-app",
            [
                self._open_pr(3, "fix: thing", "per Ask #43 answer", ["see notice #7"], ["chore: guild sync"]),
                self._open_pr(4, "feat: clean", "all good", ["lgtm"], ["feat: clean"]),
            ],
        )
        code, out, err = self.run_cli(["doctor", "--scan-prs"], None, None)
        self.assertEqual(code, 0, out + err)
        self.assertIn("warn    acme/app#3 body", out)
        self.assertIn("warn    acme/app#3 comment", out)
        self.assertIn("warn    acme/app#3 commit", out)
        self.assertNotIn("acme/app#3 title", out)
        self.assertNotIn("acme/app#4", out)
        self.assertNotIn("Ask #43", out)
        self.assertNotIn("notice #7", out)

    def test_scan_flags_title(self):
        self.write_gh_fixture("open_acme-app", [self._open_pr(5, "Guild rollout", "", [], [])])
        code, out, err = self.run_cli(["doctor", "--scan-prs"], None, None)
        self.assertEqual(code, 0)
        self.assertIn("warn    acme/app#5 title", out)

    def test_scan_handles_null_body(self):
        pr = self._open_pr(6, "feat: x", "", [], [])
        pr["body"] = None
        self.write_gh_fixture("open_acme-app", [pr])
        code, out, err = self.run_cli(["doctor", "--scan-prs"], None, None)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("acme/app#6", out)

    def test_scan_is_off_by_default(self):
        self.write_gh_fixture("open_acme-app", [self._open_pr(3, "guild", "guild", ["guild"], ["guild"])])
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 0)
        self.assertNotIn("acme/app#3", out)

    def test_gh_failure_is_a_single_warn(self):
        self.write_gh_error("open_acme-app", "gh exploded")
        code, out, err = self.run_cli(["doctor", "--scan-prs"], None, None)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(out.count("PR scan skipped"), 1)
        self.assertIn("warn    PR scan skipped", out)

    def test_scan_never_changes_failing_exit_code(self):
        (self.home / ".claude" / "GUILD.md").unlink()
        self.write_gh_fixture("open_acme-app", [self._open_pr(3, "guild", "", [], [])])
        code, out, err = self.run_cli(["doctor", "--scan-prs"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("warn    acme/app#3 title", out)
