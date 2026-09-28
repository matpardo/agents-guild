import json
import os

from guild import db, events, paths, timeutil
from tests.testutil import GuildTestCase

_SDD_CONFIG = {
    "task_heading": r"^#{2,3}\s+(T\d+\w*)\b.*?\s[—–-]\s+(.+)$",
    "key_ref": r"[A-Z]{2,10}-\d+",
    "deps_line": r"^\*\*Deps:\*\*\s*(.+)$",
    "status_line": r"^\*\*Status:\*\*\s*(.+)$",
    "key_line": r"^\*\*JIRA:\*\*\s*(.+)$",
    "epic_key_field": "jira",
    "epic_status_field": "status",
}


class DriftTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.project_root = self.root / "projects" / "acme"
        self.repo_dir = self.project_root / "repo"
        self.repo_dir.mkdir(parents=True)
        self.sdd_root = self.project_root / "sdd-docs"
        self._write_project_config()
        self.write_session(1, "sess-1", "alpha-session")
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.conn = db.connect(paths.db_path())

    def _write_project_config(self):
        projects_dir = self.config_home / "guild" / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "name": "acme",
            "paths": [str(self.project_root) + "/*"],
            "github": {"repos": ["acme/app"]},
            "sdd": dict(_SDD_CONFIG, root=str(self.sdd_root), epics_dir="epics"),
        }
        (projects_dir / "acme.json").write_text(json.dumps(data))

    def _write_epic(self, epic, frontmatter_extra, body):
        epic_dir = self.sdd_root / "epics" / epic
        epic_dir.mkdir(parents=True, exist_ok=True)
        frontmatter = "---\nepic: {}\n{}---\n\n".format(epic, frontmatter_extra)
        (epic_dir / "tasks.md").write_text(frontmatter + body)

    def _sync_sdd(self):
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def _record_cards(self, cards):
        with db.writing(self.conn):
            events.record(
                self.conn, timeutil.utcnow(), "test@host", None, None, "acme",
                "tracker.synced", "local", {"project": "acme", "cards": cards},
            )

    def _card(self, key, status_category, parent_key=None, status=None):
        return {
            "key": key,
            "status": status or status_category,
            "status_category": status_category,
            "issue_type": "Task",
            "parent_key": parent_key,
        }

    def _track_pr(self, number, quest, tid):
        self.write_gh_fixture(
            "view_acme-app_{}".format(number),
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/{}".format(number), "title": "t"},
        )
        code, out, err = self.run_cli(
            [
                "pr", "track", "acme/app#{}".format(number), "--task", "{}/{}".format(quest, tid),
                "--what", "x", "--waits", "y",
            ],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0, err)

    def _set_pr_lifecycle(self, number, lifecycle):
        with db.writing(self.conn):
            events.record(
                self.conn, timeutil.utcnow(), "test@host", None, None, None,
                "pr.synced", "guild",
                {
                    "repo": "acme/app", "number": number, "gh_state": None, "gh_draft": False,
                    "branch": None, "title": None, "checks_failing": 0, "checks_passing": 0,
                    "lifecycle": lifecycle, "synced_at": timeutil.to_iso(timeutil.utcnow()),
                },
            )

    def _drift(self, epic=None):
        argv = ["drift"]
        if epic is not None:
            argv += ["--epic", epic]
        return self.run_cli(argv, "sess-1", self.repo_dir)


class NoDriftTests(DriftTestCase):
    def test_no_findings_at_all_reports_no_drift(self):
        self._write_epic("wave0", "status: active\n", "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n")
        self._sync_sdd()
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "no drift")


class MergedPrTaskNotDoneTests(DriftTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic("wave1", "status: active\n", "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n")
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave1", "--title", "Wave 1", "--epic", "wave1", "--tasks", "T01"],
            "sess-1", self.repo_dir,
        )
        self._track_pr(1, "wave1", "T01")

    def test_merged_pr_with_task_not_done_is_a_finding(self):
        self._set_pr_lifecycle(1, "merged")
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertIn("merged PR, task not done (1)", out)
        self.assertIn("pr:acme/app#1: merged, task:wave1/T01 state=queued", out)
        self.assertIn("1 findings", out)

    def test_merged_pr_with_task_done_is_not_a_finding(self):
        self.run_cli(["task", "done", "wave1/T01"], "sess-1", self.repo_dir)
        self._set_pr_lifecycle(1, "merged")
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertNotIn("merged PR, task not done", out)
        self.assertEqual(out.strip(), "no drift")


class TrackerSddDisagreeTests(DriftTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic(
            "wave2", "status: active\n",
            "## T01 — First\n\n**JIRA:** DEMO-1\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()

    def test_card_done_and_sdd_pending_is_a_finding(self):
        self._record_cards([self._card("DEMO-1", "done", status="Listo")])
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertIn("tracker and SDD disagree (1)", out)
        self.assertIn("task:wave2/T01 (DEMO-1): tracker=done (Listo), sdd=pending", out)

    def test_card_and_sdd_agree_is_not_a_finding(self):
        self._record_cards([self._card("DEMO-1", "new")])
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertNotIn("tracker and SDD disagree", out)


class SddTaskWithoutCardTests(DriftTestCase):
    def test_keyed_epic_with_unkeyed_task_is_a_finding(self):
        self._write_epic(
            "wave3", "jira: DEMO-9\nstatus: active\n",
            "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertIn("SDD task without card (1)", out)
        self.assertIn("task:wave3/T01: no tracker key (epic wave3 is keyed DEMO-9)", out)

    def test_unkeyed_epic_with_unkeyed_task_is_not_a_finding(self):
        self._write_epic(
            "wave3b", "status: active\n", "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n"
        )
        self._sync_sdd()
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertNotIn("SDD task without card", out)


class CardNotUnderEpicTests(DriftTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic(
            "wave4", "jira: DEMO-20\nstatus: active\n",
            "## T01 — First\n\n**JIRA:** DEMO-21\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()

    def test_card_with_no_parent_is_a_finding(self):
        self._record_cards([self._card("DEMO-21", "new", parent_key=None)])
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertIn("card not under its epic (1)", out)
        self.assertIn("task:wave4/T01 (DEMO-21): card not under epic wave4 (DEMO-20) in tracker", out)

    def test_card_under_epic_is_not_a_finding(self):
        self._record_cards([self._card("DEMO-21", "new", parent_key="DEMO-20")])
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertNotIn("card not under its epic", out)


class PrOpenCardNotStartedTests(DriftTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic(
            "wave5", "status: active\n",
            "## T01 — First\n\n**JIRA:** DEMO-30\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave5", "--title", "Wave 5", "--epic", "wave5", "--tasks", "T01"],
            "sess-1", self.repo_dir,
        )
        self._track_pr(5, "wave5", "T01")

    def test_open_pr_with_card_new_is_a_finding(self):
        self._record_cards([self._card("DEMO-30", "new", status="To Do")])
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertIn("PR open, card not started (1)", out)
        self.assertIn("pr:acme/app#5 (draft): task:wave5/T01 card DEMO-30 not started (To Do)", out)

    def test_open_pr_with_card_started_is_not_a_finding(self):
        self._record_cards([self._card("DEMO-30", "indeterminate", status="In Progress")])
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertNotIn("PR open, card not started", out)


class PrClosedUnmergedTests(DriftTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic("wave6", "status: active\n", "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n")
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave6", "--title", "Wave 6", "--epic", "wave6", "--tasks", "T01"],
            "sess-1", self.repo_dir,
        )
        self._track_pr(6, "wave6", "T01")

    def test_closed_pr_is_a_finding(self):
        self._set_pr_lifecycle(6, "closed")
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertIn("PR closed unmerged (1)", out)
        self.assertIn("pr:acme/app#6: closed unmerged (task:wave6/T01)", out)

    def test_converging_pr_is_not_a_finding(self):
        self._set_pr_lifecycle(6, "converging")
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertNotIn("PR closed unmerged", out)


class PartyWithoutLeaderTests(DriftTestCase):
    def test_active_party_with_no_matching_session_is_a_finding(self):
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertIn("party has no running leader (1)", out)
        self.assertIn("party beta: leader session not running: resume or hand off", out)

    def test_awaiting_leader_party_is_not_a_finding(self):
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        self.run_cli(
            ["handoff", "--in-flight", "still going", "--learned", "nothing new"],
            "sess-2", self.repo_dir,
        )
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertNotIn("party has no running leader", out)

    def test_party_with_matching_session_is_not_a_finding(self):
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertNotIn("party has no running leader", out)


class EpicDoneWithOpenWorkTests(DriftTestCase):
    def test_done_epic_with_pending_task_is_a_finding(self):
        self._write_epic("wave8", "status: done\n", "## T01 — First\n\n**Deps:** —\n**Status:** [x] done\n")
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave8", "--title", "Wave 8", "--epic", "wave8", "--tasks", "T01"],
            "sess-1", self.repo_dir,
        )
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertIn("epic done with open work (1)", out)
        self.assertIn("epic wave8 sdd_status=done but task:wave8/T01 state=queued", out)

    def test_done_epic_with_open_pr_is_a_finding(self):
        self._write_epic("wave8b", "status: done\n", "## T01 — First\n\n**Deps:** —\n**Status:** [x] done\n")
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave8b", "--title", "Wave 8b", "--epic", "wave8b", "--tasks", "T01"],
            "sess-1", self.repo_dir,
        )
        self.run_cli(["task", "done", "wave8b/T01"], "sess-1", self.repo_dir)
        self._track_pr(8, "wave8b", "T01")
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertIn("epic done with open work (1)", out)
        self.assertIn("epic wave8b sdd_status=done but pr:acme/app#8 lifecycle=draft", out)

    def test_done_epic_with_all_done_and_no_open_pr_is_not_a_finding(self):
        self._write_epic("wave8c", "status: done\n", "## T01 — First\n\n**Deps:** —\n**Status:** [x] done\n")
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave8c", "--title", "Wave 8c", "--epic", "wave8c", "--tasks", "T01"],
            "sess-1", self.repo_dir,
        )
        self.run_cli(["task", "done", "wave8c/T01"], "sess-1", self.repo_dir)
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertNotIn("epic done with open work", out)

    def test_active_epic_with_pending_task_is_not_a_finding(self):
        self._write_epic("wave8d", "status: active\n", "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n")
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave8d", "--title", "Wave 8d", "--epic", "wave8d", "--tasks", "T01"],
            "sess-1", self.repo_dir,
        )
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertNotIn("epic done with open work", out)


class EpicFilterTests(DriftTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic(
            "wave9", "jira: DEMO-90\nstatus: active\n",
            "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._write_epic(
            "wave10", "jira: DEMO-100\nstatus: active\n",
            "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()

    def test_epic_filter_restricts_findings_to_that_epic(self):
        code, out, err = self._drift(epic="wave9")
        self.assertEqual(code, 0, err)
        self.assertIn("task:wave9/T01: no tracker key", out)
        self.assertNotIn("wave10", out)

    def test_no_filter_reports_both_epics(self):
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertIn("task:wave9/T01: no tracker key", out)
        self.assertIn("task:wave10/T01: no tracker key", out)


class NoNetworkTests(DriftTestCase):
    def test_drift_never_invokes_gh_or_acli(self):
        self._write_epic(
            "wave11", "jira: DEMO-110\nstatus: done\n",
            "## T01 — First\n\n**JIRA:** DEMO-111\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()
        self._record_cards([self._card("DEMO-111", "new")])
        self.run_cli(
            ["quest", "add", "wave11", "--title", "Wave 11", "--epic", "wave11", "--tasks", "T01"],
            "sess-1", self.repo_dir,
        )
        self._track_pr(11, "wave11", "T01")

        original_path = os.environ["PATH"]
        stripped = os.pathsep.join(
            part for part in original_path.split(os.pathsep) if part != str(self.bin_dir)
        )
        os.environ["PATH"] = stripped
        try:
            code, out, err = self._drift()
        finally:
            os.environ["PATH"] = original_path
        self.assertEqual(code, 0, err)
        self.assertIn("findings", out)


if __name__ == "__main__":
    import unittest

    unittest.main()
