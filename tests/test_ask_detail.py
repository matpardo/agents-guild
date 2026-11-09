import json

from guild import ask_detail, db, paths
from tests.testutil import GuildTestCase


class AskDetailBase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
        self.write_session(111, "sess-1", "alpha-g1")
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.conn = db.connect(paths.db_path())

    def configure(self, **extra):
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data.update(extra)
        config_file.write_text(json.dumps(data))

    def make_epic_quest(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "widget",
            "## T01 — First (PROJ-12)\n\n**Deps:** —\n\n**Status:** [ ] pending\n",
        )
        self.run_cli(
            ["quest", "add", "wq", "--title", "W", "--epic", "widget", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )

    def insert_card(self, key, status):
        with db.writing(self.conn):
            self.conn.execute(
                "INSERT INTO cards (project, key, status, status_category, issue_type)"
                " VALUES ('acme', ?, ?, 'indeterminate', 'Task')",
                (key, status),
            )

    def ask(self, *refs):
        args = ["ask", "Should the retry cap be 3 or 5?", "--context", "Both pass CI."]
        for ref in refs:
            args.extend(["--ref", ref])
        code, out, err = self.run_cli(args + ["--option", "3", "--option", "5"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def model(self, ask_id):
        row = self.conn.execute("SELECT * FROM asks WHERE id = ?", (ask_id,)).fetchone()
        ctx = _Ctx(self.conn, self)
        return ask_detail.build(ctx, row)


class _Ctx:
    def __init__(self, conn, case):
        self.conn = conn
        self.projects_dir = case.config_home / "guild" / "projects"


class SddPathTests(AskDetailBase):
    def test_root_mode_paths(self):
        self.make_epic_quest()
        self.ask("task:wq/T01")
        task = self.model(1)["refs"][0]
        sdd_root = self.root / "sdd-acme"
        self.assertEqual(task["spec"], str(sdd_root / "epics" / "widget" / "spec.md"))
        self.assertEqual(task["tasks"], str(sdd_root / "epics" / "widget" / "tasks.md"))
        self.assertEqual((task["epic"], task["state"], task["title"]), ("widget", "queued", "First (PROJ-12)"))

    def test_git_mode_paths(self):
        self.make_epic_quest()
        self.ask("task:wq/T01")
        self.configure(sdd={"git_repo": "/x/y", "git_ref": "origin/main", "epics_dir": "epics"})
        task = self.model(1)["refs"][0]
        self.assertEqual(task["spec"], "git:origin/main:epics/widget/spec.md")
        self.assertEqual(task["tasks"], "git:origin/main:epics/widget/tasks.md")

    def test_no_sdd_config_means_no_paths(self):
        self.ask("task:demo/T01")
        task = self.model(1)["refs"][0]
        self.assertIsNone(task["spec"])
        self.assertIsNone(task["tasks"])

    def test_no_epic_means_no_paths(self):
        self.configure(sdd={"root": str(self.root / "sdd"), "epics_dir": "epics"})
        self.ask("task:demo/T01")
        task = self.model(1)["refs"][0]
        self.assertIsNone(task["spec"])


class CardRefTests(AskDetailBase):
    def test_card_with_status_and_url(self):
        self.insert_card("PROJ-12", "In Progress")
        self.configure(tracker={"kind": "jira-acli", "browse_url": "https://tracker.example.com/browse/"})
        self.ask("card:PROJ-12")
        card = self.model(1)["refs"][0]
        self.assertEqual(card["status"], "In Progress")
        self.assertEqual(card["url"], "https://tracker.example.com/browse/PROJ-12")

    def test_card_without_browse_url_has_no_link(self):
        self.insert_card("PROJ-12", "In Progress")
        self.ask("card:PROJ-12")
        self.assertIsNone(self.model(1)["refs"][0]["url"])

    def test_missing_card_is_marked(self):
        self.insert_card("PROJ-12", "In Progress")
        self.ask("card:PROJ-12")
        with db.writing(self.conn):
            self.conn.execute("DELETE FROM cards")
        card = self.model(1)["refs"][0]
        self.assertTrue(card["missing"])


class MissingTargetTests(AskDetailBase):
    def test_missing_task_and_pr_are_marked(self):
        self.ask("task:demo/T01")
        with db.writing(self.conn):
            self.conn.execute("DELETE FROM quest_tasks")
        task = self.model(1)["refs"][0]
        self.assertEqual(task, {"kind": "task", "ref": "task:demo/T01", "quest": "demo", "tid": "T01", "missing": True})

    def test_missing_pr_is_marked_with_url(self):
        self.ask("task:demo/T01")
        with db.writing(self.conn):
            self.conn.execute("UPDATE asks SET refs = ? WHERE id = 1", (json.dumps(["pr:acme/app#99"]),))
        pr = self.model(1)["refs"][0]
        self.assertTrue(pr["missing"])
        self.assertEqual(pr["url"], "https://github.com/acme/app/pull/99")


class PrRefTests(AskDetailBase):
    def test_pr_fields(self):
        self.write_gh_fixture(
            "view_acme-app_41",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/41", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#41", "--task", "demo/T01", "--what", "x", "--waits", "review"],
            "sess-1",
            self.repo_dir,
        )
        with db.writing(self.conn):
            self.conn.execute("UPDATE prs SET checks_passing = 2, checks_failing = 1, checks_pending = 0")
        self.ask("pr:acme/app#41")
        pr = self.model(1)["refs"][0]
        self.assertEqual(
            pr,
            {
                "kind": "pr",
                "ref": "pr:acme/app#41",
                "url": "https://github.com/acme/app/pull/41",
                "lifecycle": "draft",
                "checks_failing": 1,
                "checks_passing": 2,
                "checks_pending": 0,
                "waits": "review",
            },
        )


class OriginAndResumeTests(AskDetailBase):
    def write_transcript(self):
        directory = self.claude_projects_dir / "proj"
        directory.mkdir()
        (directory / "sess-1.jsonl").write_text("{}\n")

    def test_resume_command_with_transcript(self):
        self.write_transcript()
        self.ask("task:demo/T01")
        resume_text = self.model(1)["resume"]
        self.assertTrue(resume_text.startswith("claude --resume sess-1 --name alpha-g1"))
        self.assertNotIn("transcript not found", resume_text)

    def test_resume_notes_missing_transcript(self):
        self.ask("task:demo/T01")
        self.assertTrue(self.model(1)["resume"].endswith(" (transcript not found)"))

    def test_no_snapshot_means_no_origin_and_no_resume(self):
        self.ask("task:demo/T01")
        with db.writing(self.conn):
            self.conn.execute("UPDATE asks SET snapshot = NULL")
        model = self.model(1)
        self.assertIsNone(model["origin"])
        self.assertIsNone(model["resume"])
        self.assertIn("origin: not recorded", ask_detail.render_lines(model))

    def test_missing_project_config_still_builds(self):
        self.ask("task:demo/T01")
        (self.config_home / "guild" / "projects" / "acme.json").unlink()
        self.assertEqual(self.model(1)["refs"][0]["spec"], None)


class CliTests(AskDetailBase):
    def test_golden_output(self):
        self.insert_card("PROJ-12", "In Progress")
        self.configure(
            tracker={"kind": "jira-acli", "browse_url": "https://tracker.example.com/browse/"},
        )
        self.make_epic_quest()
        self.ask("task:wq/T01", "card:PROJ-12")
        code, out, err = self.run_cli(["asks", "1"], None, None)
        self.assertEqual(code, 0, err)
        sdd_root = self.root / "sdd-acme"
        lines = out.splitlines()
        self.assertEqual(lines[0].split(" · created")[0], "ask #1 · alpha · open")
        self.assertEqual(
            lines[1:8],
            [
                "  Should the retry cap be 3 or 5?",
                "  context:",
                "    Both pass CI.",
                "  options: 3 | 5",
                "task    wq/T01  First (PROJ-12)  [queued]  epic: widget",
                "card    PROJ-12  In Progress  https://tracker.example.com/browse/PROJ-12",
                "dig in",
            ],
        )
        self.assertEqual(lines[8], "  spec:  {}".format(sdd_root / "epics" / "widget" / "spec.md"))
        self.assertEqual(lines[9], "  tasks: {}".format(sdd_root / "epics" / "widget" / "tasks.md"))
        self.assertEqual(lines[10], "origin (at creation)")
        self.assertEqual(lines[11], "  session: sess-1 (alpha-g1)")
        self.assertIn("resume: claude --resume sess-1 --name alpha-g1", out)
        self.assertNotIn("recent events", out)
        self.assertNotIn("epics:", out)
        self.assertNotIn("recommend", out)
        self.assertEqual(lines[-1], '  → guild answer 1 "..."')

    def test_recommend_renders_before_refs_when_set(self):
        self.run_cli(
            ["ask", "Which cap?", "--context", "ctx", "--ref", "task:demo/T01", "--recommend", "Pick **3**"],
            "sess-1",
            self.repo_dir,
        )
        code, out, err = self.run_cli(["asks", "1"], None, None)
        lines = out.splitlines()
        self.assertEqual(lines[lines.index("  recommend:") + 1], "    Pick **3**")
        self.assertLess(lines.index("  recommend:"), lines.index("dig in"))

    def test_answered_ask_shows_answer_instead_of_hint(self):
        self.ask("task:demo/T01")
        self.run_cli(["answer", "1", "five\nsix\n\nseven"], None, None)
        code, out, err = self.run_cli(["asks", "1"], None, None)
        self.assertIn("  answer:\n    five\n    six\n\n    seven\n", out)
        self.assertIn("  answered: ", out)
        self.assertNotIn("guild answer", out)

    def test_unknown_id(self):
        code, out, err = self.run_cli(["asks", "9"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("unknown ask #9", err)

    def test_id_with_filters_is_an_error(self):
        self.ask("task:demo/T01")
        for extra in (["--all"], ["--party", "alpha"], ["--since", "1d"]):
            code, out, err = self.run_cli(["asks", "1"] + extra, None, None)
            self.assertEqual(code, 1)
            self.assertIn("guild asks <id> takes no filters", err)

    def test_missing_task_renders_marker(self):
        self.ask("task:demo/T01")
        with db.writing(self.conn):
            self.conn.execute("DELETE FROM quest_tasks")
        code, out, err = self.run_cli(["asks", "1"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("task    demo/T01  (not found)", out)

    def test_control_sequences_are_stripped(self):
        self.ask("task:demo/T01")
        with db.writing(self.conn):
            self.conn.execute("UPDATE quest_tasks SET title = ?", ("First\x1b[31m",))
        model = self.model(1)
        self.assertEqual(model["refs"][0]["title"], "First")
        code, out, err = self.run_cli(["asks", "1"], None, None)
        self.assertNotIn("\x1b", out)
