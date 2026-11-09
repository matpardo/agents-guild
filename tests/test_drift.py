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
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
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
                self.conn,
                timeutil.utcnow(),
                "test@host",
                None,
                None,
                "acme",
                "tracker.synced",
                "local",
                {"project": "acme", "cards": cards},
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
                "pr",
                "track",
                "acme/app#{}".format(number),
                "--task",
                "{}/{}".format(quest, tid),
                "--what",
                "x",
                "--waits",
                "y",
            ],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)

    def _set_pr_lifecycle(self, number, lifecycle):
        with db.writing(self.conn):
            events.record(
                self.conn,
                timeutil.utcnow(),
                "test@host",
                None,
                None,
                None,
                "pr.synced",
                "guild",
                {
                    "repo": "acme/app",
                    "number": number,
                    "gh_state": None,
                    "gh_draft": False,
                    "branch": None,
                    "title": None,
                    "checks_failing": 0,
                    "checks_passing": 0,
                    "lifecycle": lifecycle,
                    "synced_at": timeutil.to_iso(timeutil.utcnow()),
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
        self.assertEqual(out.strip(), "scope: no epics in active quests\nno drift")


class MergedPrTaskNotDoneTests(DriftTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic("wave1", "status: active\n", "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n")
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave1", "--title", "Wave 1", "--epic", "wave1", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
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
        self._write_epic("wave1", "status: active\n", "## T01 — First\n\n**Deps:** —\n**Status:** [x] done\n")
        self._sync_sdd()
        self.run_cli(["task", "done", "wave1/T01"], "sess-1", self.repo_dir)
        self._set_pr_lifecycle(1, "merged")
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertNotIn("merged PR, task not done", out)
        self.assertEqual(
            out.strip(),
            "scope: 1 epics in active quests (use --all for the whole project)\nno drift",
        )


class TrackerSddDisagreeTests(DriftTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic(
            "wave2",
            "status: active\n",
            "## T01 — First\n\n**JIRA:** DEMO-1\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave2", "--title", "Wave 2", "--epic", "wave2", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )

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
            "wave3",
            "jira: DEMO-9\nstatus: active\n",
            "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave3", "--title", "Wave 3", "--epic", "wave3", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertIn("SDD task without card (1)", out)
        self.assertIn("task:wave3/T01: no tracker key (epic wave3 is keyed DEMO-9)", out)

    def test_unkeyed_epic_with_unkeyed_task_is_not_a_finding(self):
        self._write_epic("wave3b", "status: active\n", "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n")
        self._sync_sdd()
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertNotIn("SDD task without card", out)


class CardNotUnderEpicTests(DriftTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic(
            "wave4",
            "jira: DEMO-20\nstatus: active\n",
            "## T01 — First\n\n**JIRA:** DEMO-21\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave4", "--title", "Wave 4", "--epic", "wave4", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )

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
            "wave5",
            "status: active\n",
            "## T01 — First\n\n**JIRA:** DEMO-30\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave5", "--title", "Wave 5", "--epic", "wave5", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
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
            "sess-1",
            self.repo_dir,
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
        self.run_cli(
            ["party", "start", "beta", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-2",
            self.repo_dir,
        )
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertIn("party has no running leader (1)", out)
        self.assertIn("party beta: leader session not running: resume or hand off", out)

    def test_awaiting_leader_party_is_not_a_finding(self):
        self.run_cli(
            ["party", "start", "beta", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-2",
            self.repo_dir,
        )
        self.run_cli(
            ["handoff", "--in-flight", "still going", "--learned", "nothing new"],
            "sess-2",
            self.repo_dir,
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
            "sess-1",
            self.repo_dir,
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
            "sess-1",
            self.repo_dir,
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
            "sess-1",
            self.repo_dir,
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
            "sess-1",
            self.repo_dir,
        )
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertNotIn("epic done with open work", out)


class QuestTaskNotInSddTests(DriftTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic("wave9", "status: active\n", "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n")
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave9", "--title", "Wave 9", "--epic", "wave9", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )

    def test_task_added_to_an_epic_quest_but_not_to_the_sdd_is_a_finding(self):
        self.run_cli(
            ["task", "add", "wave9/T09", "--title", "Extra", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        code, out, err = self._drift("wave9")
        self.assertEqual(code, 0, err)
        self.assertIn("quest task not in SDD (1)", out)
        self.assertIn("task:wave9/T09: not in epic wave9 tasks.md, add it", out)

    def test_no_sdd_task_is_not_a_finding(self):
        self.run_cli(
            ["task", "add", "wave9/T09", "--title", "Extra", "--no-sdd", "--reason", "serves the goal"],
            "sess-1",
            self.repo_dir,
        )
        code, out, err = self._drift("wave9")
        self.assertNotIn("quest task not in SDD", out)

    def test_discarded_task_missing_from_the_sdd_is_not_a_finding(self):
        self.run_cli(
            ["task", "add", "wave9/T09", "--title", "Extra", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.run_cli(["task", "discard", "wave9/T09", "--reason", "mistake"], "sess-1", self.repo_dir)
        code, out, err = self._drift("wave9")
        self.assertNotIn("quest task not in SDD", out)
        self.assertNotIn("discarded task in SDD", out)

    def test_discarded_task_still_in_the_sdd_is_a_finding(self):
        self.run_cli(["task", "discard", "wave9/T01", "--reason", "mistake"], "sess-1", self.repo_dir)
        code, out, err = self._drift("wave9")
        self.assertIn("discarded task in SDD (1)", out)
        self.assertIn("task:wave9/T01 discarded but still listed in epic wave9 tasks.md", out)

    def test_discarded_no_sdd_task_is_not_a_finding(self):
        self.run_cli(
            ["task", "add", "wave9/T09", "--title", "Extra", "--no-sdd", "--reason", "serves the goal"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["task", "discard", "wave9/T09", "--reason", "mistake"], "sess-1", self.repo_dir)
        code, out, err = self._drift("wave9")
        self.assertNotIn("discarded task in SDD", out)

    def test_restored_task_is_no_longer_a_finding(self):
        self.run_cli(["task", "discard", "wave9/T01", "--reason", "mistake"], "sess-1", self.repo_dir)
        self.run_cli(["task", "restore", "wave9/T01"], "sess-1", self.repo_dir)
        code, out, err = self._drift("wave9")
        self.assertNotIn("discarded task in SDD", out)

    def test_quest_done_gate_reports_a_discarded_task_still_in_the_sdd(self):
        self.run_cli(["task", "discard", "wave9/T01", "--reason", "mistake"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["quest", "done", "wave9"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("discarded but still listed", err)

    def test_quest_done_passes_with_a_done_no_sdd_task(self):
        self.run_cli(
            ["task", "add", "wave9/T09", "--title", "Extra", "--no-sdd", "--reason", "serves the goal"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["task", "done", "wave9/T09"], "sess-1", self.repo_dir)
        self.run_cli(["task", "done", "wave9/T01"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["quest", "done", "wave9"], "sess-1", self.repo_dir)
        self.assertNotIn("not in epic", err)

    def test_quest_done_is_refused_while_a_no_sdd_task_is_open(self):
        self.run_cli(
            ["task", "add", "wave9/T09", "--title", "Extra", "--no-sdd", "--reason", "serves the goal"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["task", "done", "wave9/T01"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["quest", "done", "wave9"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("T09", err)

    def test_task_present_in_the_sdd_is_not_a_finding(self):
        self.run_cli(
            ["task", "add", "wave9/T09", "--title", "Extra", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self._write_epic(
            "wave9",
            "status: active\n",
            "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n\n"
            "## T09 — Extra\n\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()
        code, out, err = self._drift("wave9")
        self.assertNotIn("quest task not in SDD", out)

    def test_no_epic_quest_task_is_not_a_finding(self):
        self.run_cli(["quest", "add", "free", "--title", "Free", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "free/A", "--title", "A", "--reason", "serves the goal"], "sess-1", self.repo_dir)
        code, out, err = self._drift("wave9")
        self.assertNotIn("quest task not in SDD", out)

    def test_quest_done_is_refused_while_the_task_is_missing_from_the_sdd(self):
        self.run_cli(
            ["task", "add", "wave9/T09", "--title", "Extra", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.run_cli(["task", "done", "wave9/T09"], "sess-1", self.repo_dir)
        self.run_cli(["task", "done", "wave9/T01"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["quest", "done", "wave9"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("task:wave9/T09: not in epic wave9 tasks.md", err)


class TaskDoneSddNotDoneTests(DriftTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic("wave10", "status: active\n", "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n")
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave10", "--title", "Wave 10", "--epic", "wave10", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["task", "done", "wave10/T01"], "sess-1", self.repo_dir)

    def test_done_task_with_pending_sdd_is_a_finding(self):
        code, out, err = self._drift("wave10")
        self.assertEqual(code, 0, err)
        self.assertIn("task done, SDD not done (1)", out)
        self.assertIn("task:wave10/T01 done, epic wave10 tasks.md says pending", out)

    def test_done_task_with_done_sdd_is_not_a_finding(self):
        self._write_epic("wave10", "status: active\n", "## T01 — First\n\n**Deps:** —\n**Status:** [x] done\n")
        self._sync_sdd()
        code, out, err = self._drift("wave10")
        self.assertNotIn("task done, SDD not done", out)

    def test_quest_done_is_refused_while_the_sdd_is_not_done(self):
        code, out, err = self.run_cli(["quest", "done", "wave10"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("task:wave10/T01 done, epic wave10 tasks.md says pending", err)


class EpicFilterTests(DriftTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic(
            "wave9",
            "jira: DEMO-90\nstatus: active\n",
            "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._write_epic(
            "wave10",
            "jira: DEMO-100\nstatus: active\n",
            "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave9", "--title", "Wave 9", "--epic", "wave9", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(
            ["quest", "add", "wave10", "--title", "Wave 10", "--epic", "wave10", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )

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
            "wave11",
            "jira: DEMO-110\nstatus: done\n",
            "## T01 — First\n\n**JIRA:** DEMO-111\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()
        self._record_cards([self._card("DEMO-111", "new")])
        self.run_cli(
            ["quest", "add", "wave11", "--title", "Wave 11", "--epic", "wave11", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        self._track_pr(11, "wave11", "T01")

        original_path = os.environ["PATH"]
        stripped = os.pathsep.join(part for part in original_path.split(os.pathsep) if part != str(self.bin_dir))
        os.environ["PATH"] = stripped
        try:
            code, out, err = self._drift()
        finally:
            os.environ["PATH"] = original_path
        self.assertEqual(code, 0, err)
        self.assertIn("findings", out)


class DefaultScopeTests(DriftTestCase):
    def test_epic_without_active_quest_excluded_by_default_and_included_with_all(self):
        self._write_epic(
            "wave20",
            "jira: DEMO-200\nstatus: active\n",
            "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertNotIn("wave20", out)
        code, out, err = self.run_cli(["drift", "--all"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("task:wave20/T01: no tracker key", out)

    def test_scope_line_default_with_no_epics_in_active_quests(self):
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], "scope: no epics in active quests")

    def test_scope_line_default_with_epics_in_active_quests(self):
        self._write_epic("wave21", "status: active\n", "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n")
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave21", "--title", "Wave 21", "--epic", "wave21", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], "scope: 1 epics in active quests (use --all for the whole project)")

    def test_scope_line_all(self):
        code, out, err = self.run_cli(["drift", "--all"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], "scope: whole project")

    def test_scope_line_epic_filter(self):
        code, out, err = self._drift(epic="somewhere")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], "scope: epic somewhere")

    def test_epic_and_all_are_mutually_exclusive(self):
        code, out, err = self.run_cli(["drift", "--epic", "somewhere", "--all"], "sess-1", self.repo_dir)
        self.assertEqual(code, 2)


if __name__ == "__main__":
    import unittest

    unittest.main()


class CardLagTests(DriftTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic(
            "wave9",
            "status: active\n",
            "## T01 — First\n\n**JIRA:** DEMO-90\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave9", "--title", "Wave 9", "--epic", "wave9", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )

    def _track_with_card(self, number, card):
        self.write_gh_fixture(
            "view_acme-app_{}".format(number),
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/{}".format(number), "title": "t"},
        )
        self.track_legacy_card_pr("alpha", "acme/app", number, card, "x", "y", "feature/{}".format(number))

    def test_started_task_with_new_card_is_a_finding(self):
        self._record_cards([self._card("DEMO-90", "new", status="To Do")])
        self.run_cli(["task", "start", "wave9/T01", "--summary", "go"], "sess-1", self.repo_dir)
        code, out, err = self._drift()
        self.assertEqual(code, 0, err)
        self.assertIn("task started, card not started (1)", out)
        self.assertIn("task:wave9/T01 started, card DEMO-90 not started (To Do): move DEMO-90 to In Progress", out)

    def test_started_task_with_card_in_progress_is_not_a_finding(self):
        self._record_cards([self._card("DEMO-90", "indeterminate")])
        self.run_cli(["task", "start", "wave9/T01", "--summary", "go"], "sess-1", self.repo_dir)
        code, out, err = self._drift()
        self.assertNotIn("task started, card not started", out)

    def test_queued_task_with_new_card_is_not_a_finding(self):
        self._record_cards([self._card("DEMO-90", "new")])
        code, out, err = self._drift()
        self.assertNotIn("task started, card not started", out)

    def test_merged_pr_with_card_not_done_is_a_finding(self):
        self._record_cards([self._card("DEMO-90", "indeterminate", status="In Progress")])
        self._track_pr(9, "wave9", "T01")
        self._set_pr_lifecycle(9, "merged")
        code, out, err = self._drift()
        self.assertIn("PR merged, card not done (1)", out)
        self.assertIn(
            "card DEMO-90 not done (In Progress): move DEMO-90 to Done; merged pr:acme/app#9 task:wave9/T01",
            out,
        )

    def test_untracked_merged_pr_drops_the_card_finding(self):
        self._record_cards([self._card("DEMO-90", "indeterminate", status="In Progress")])
        self._track_pr(9, "wave9", "T01")
        self._set_pr_lifecycle(9, "merged")
        code, out, err = self.run_cli(["pr", "untrack", "acme/app#9"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        code, out, err = self._drift()
        self.assertNotIn("PR merged, card not done", out)

    def test_relinked_merged_pr_drops_the_card_finding(self):
        self._record_cards([self._card("DEMO-90", "indeterminate", status="In Progress")])
        self.run_cli(["quest", "add", "loose", "--title", "Loose", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "loose/T01", "--title", "Spec", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self._track_pr(9, "wave9", "T01")
        self._set_pr_lifecycle(9, "merged")
        code, out, err = self.run_cli(["pr", "set", "acme/app#9", "--task", "loose/T01"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        code, out, err = self._drift()
        self.assertNotIn("PR merged, card not done", out)

    def test_merged_prs_on_one_card_are_one_finding(self):
        self._record_cards([self._card("DEMO-90", "indeterminate", status="In Progress")])
        self._track_pr(9, "wave9", "T01")
        self._track_pr(11, "wave9", "T01")
        self._track_with_card(12, "DEMO-90")
        for number in (9, 11, 12):
            self._set_pr_lifecycle(number, "merged")
        code, out, err = self._drift()
        self.assertIn("PR merged, card not done (1)", out)
        self.assertIn(
            "card DEMO-90 not done (In Progress): move DEMO-90 to Done;"
            " merged pr:acme/app#9 task:wave9/T01, pr:acme/app#11 task:wave9/T01, pr:acme/app#12",
            out,
        )

    def test_merged_pr_with_card_done_is_not_a_finding(self):
        self._record_cards([self._card("DEMO-90", "done")])
        self._track_pr(9, "wave9", "T01")
        self._set_pr_lifecycle(9, "merged")
        code, out, err = self._drift()
        self.assertNotIn("PR merged, card not done", out)

    def test_card_flag_pr_without_task_is_checked(self):
        self._record_cards([self._card("DEMO-91", "new", status="To Do")])
        self._track_with_card(10, "DEMO-91")
        code, out, err = self._drift()
        self.assertIn("pr:acme/app#10 (draft): card DEMO-91 not started (To Do): move DEMO-91 to In Progress", out)
        self._set_pr_lifecycle(10, "merged")
        code, out, err = self._drift()
        self.assertIn("card DEMO-91 not done (To Do): move DEMO-91 to Done; merged pr:acme/app#10", out)

    def test_card_flag_pr_with_card_started_is_not_a_finding(self):
        self._record_cards([self._card("DEMO-91", "indeterminate")])
        self._track_with_card(10, "DEMO-91")
        code, out, err = self._drift()
        self.assertNotIn("PR open, card not started", out)

    def test_card_flag_pr_is_outside_an_epic_scope(self):
        self._record_cards([self._card("DEMO-91", "new")])
        self._track_with_card(10, "DEMO-91")
        code, out, err = self._drift("wave9")
        self.assertNotIn("PR open, card not started", out)
