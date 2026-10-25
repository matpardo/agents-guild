from guild import context, db, paths, timeutil
from guild.commands import board as board_commands
from guild.commands import drift as drift_commands
from tests.test_drift import DriftTestCase

_EPIC = (
    "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n\n"
    "## T02 — Second\n\n**Deps:** —\n**Status:** [ ] pending\n"
)


class CloseBlockersTestCase(DriftTestCase):
    def setUp(self):
        super().setUp()
        self.write_session(2, "sess-2", "beta-session")
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-2", self.repo_dir)
        self._write_epic("wave8", "status: active\n", _EPIC)
        self._sync_sdd()
        self._add_quest("sess-1", "alpha-q", "T01")
        self._add_quest("sess-2", "beta-q", "T02")

    def _add_quest(self, session, slug, tid):
        code, out, err = self.run_cli(
            ["quest", "add", slug, "--title", "Quest " + slug, "--epic", "wave8", "--tasks", tid],
            session,
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)

    def _alpha_task_done(self):
        code, out, err = self.run_cli(["task", "done", "alpha-q/T01", "--summary", "shipped"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def _beta_merged_pr(self):
        self.write_gh_fixture(
            "view_acme-app_7",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/7", "title": "t"},
        )
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#7", "--task", "beta-q/T02", "--what", "x", "--waits", "y"],
            "sess-2",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        self._set_pr_lifecycle(7, "merged")

    def _quest_model(self, slug):
        conn = db.connect(paths.db_path())
        ctx = context.RunContext(
            conn,
            None,
            None,
            timeutil.utcnow(),
            None,
            paths.claude_sessions_dir(),
            paths.projects_config_dir(),
            paths.state_dir(),
        )
        model = board_commands.board_model(ctx)
        conn.close()
        quests = [quest for party in model["parties"] for quest in party["quests"]]
        return [quest for quest in quests if quest["slug"] == slug][0]


class EpicFindingsByOwnerTests(CloseBlockersTestCase):
    def test_splits_own_and_foreign_findings(self):
        self._alpha_task_done()
        self._beta_merged_pr()
        split = drift_commands.epic_findings_by_owner(self.conn, "acme", "wave8", "alpha")
        self.assertEqual(len(split["own"]), 1)
        self.assertIn("task:alpha-q/T01", split["own"][0])
        self.assertEqual(len(split["foreign"]), 1)
        self.assertEqual(split["foreign"][0]["party"], "beta")
        self.assertIn("pr:acme/app#7", split["foreign"][0]["text"])

    def test_no_drift_gives_empty_lists(self):
        split = drift_commands.epic_findings_by_owner(self.conn, "acme", "wave8", "alpha")
        self.assertEqual(split, {"own": [], "foreign": []})


class QuestDoneRefusalTests(CloseBlockersTestCase):
    def test_refusal_lists_other_parties_with_their_name(self):
        self._alpha_task_done()
        self._beta_merged_pr()
        code, out, err = self.run_cli(["quest", "done", "alpha-q"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("fix it or pass --accept-drift:", err)
        self.assertIn("yours:", err)
        self.assertIn("other parties:", err)
        self.assertIn("(party beta)", err)

    def test_refusal_omits_empty_yours_section(self):
        self._alpha_task_done()
        self._write_epic("wave8", "status: active\n", _EPIC.replace("[ ] pending\n\n## T02", "[x] done\n\n## T02", 1))
        self._sync_sdd()
        self._beta_merged_pr()
        code, out, err = self.run_cli(["quest", "done", "alpha-q"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertNotIn("yours:", err)
        self.assertIn("other parties:", err)


class QuestCloseBlockersModelTests(CloseBlockersTestCase):
    def test_all_done_quest_with_drift_has_close_blockers(self):
        self._alpha_task_done()
        self._beta_merged_pr()
        blockers = self._quest_model("alpha-q")["close_blockers"]
        self.assertEqual(len(blockers["own"]), 1)
        self.assertEqual(blockers["foreign"][0]["party"], "beta")

    def test_quest_with_open_tasks_has_none(self):
        self._beta_merged_pr()
        self.assertIsNone(self._quest_model("alpha-q")["close_blockers"])

    def test_all_done_quest_without_drift_has_none(self):
        self._write_epic("wave8", "status: active\n", _EPIC.replace("[ ] pending", "[x] done"))
        self._sync_sdd()
        self._alpha_task_done()
        self.assertIsNone(self._quest_model("alpha-q")["close_blockers"])

    def test_quest_without_epic_has_none(self):
        code, out, err = self.run_cli(
            ["quest", "add", "plain-q", "--title", "Plain", "--no-epic", "--tasks", "T01"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        self.run_cli(["task", "done", "plain-q/T01", "--summary", "s"], "sess-1", self.repo_dir)
        self.assertIsNone(self._quest_model("plain-q")["close_blockers"])


class QuestCloseBlockersTextBoardTests(CloseBlockersTestCase):
    def test_text_board_shows_the_blocker_line(self):
        self._alpha_task_done()
        self._beta_merged_pr()
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("can't close: drift (1 yours, 1 other parties)", out)
        self.assertIn("other parties: ", out)
        self.assertIn("(party beta)", out)
