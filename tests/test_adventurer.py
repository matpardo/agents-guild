import sqlite3

from guild import paths
from tests.mq_fixtures import OPEN_VIEW, TASKS_MD
from tests.testutil import GuildTestCase


class AdventurerTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        code, out, err = self.sync_sdd(self.repo_dir, None, "acme", "demo-epic", TASKS_MD)
        self.assertEqual(code, 0, err)

    def cli(self, argv, session_id):
        return self.run_cli(argv, session_id, self.repo_dir)

    def start(self, session_id, job, *extra):
        return self.cli(["adventurer", "start", job, "--reason", "test reason"] + list(extra), session_id)

    def rows(self, sql):
        conn = sqlite3.connect(str(paths.db_path()))
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        return conn.execute(sql).fetchall()


class AdventurerCommandTests(AdventurerTestCase):
    def test_start_then_show_and_list(self):
        code, out, err = self.start("adv-1", "fix typo", "--task", "demo-epic/T02")
        self.assertEqual(code, 0, err)
        self.assertIn("adventurer 1 started", out)
        code, out, err = self.cli(["adventurers"], None)
        self.assertEqual(code, 0, err)
        for expected in ("1", "fix typo", "demo-epic/T02", "acme", "active"):
            self.assertIn(expected, out)
        code, out, err = self.cli(["adventurers", "1"], None)
        self.assertEqual(code, 0, err)
        self.assertIn("fix typo", out)
        self.assertIn("demo-epic/T02", out)

    def test_start_requires_a_session_and_a_job(self):
        self.assertEqual(self.start(None, "x")[0], 1)
        self.assertEqual(self.start("adv-1", "  ")[0], 1)
        self.assertEqual(self.start("adv-1", "mail me@x.com")[0], 1)

    def test_start_refuses_unregistered_project(self):
        code, out, err = self.run_cli(["adventurer", "start", "x", "--reason", "test reason"], "adv-1", self.root)
        self.assertEqual(code, 1)

    def test_start_refuses_party_leader_and_second_start(self):
        self.cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1")
        code, out, err = self.start("sess-1", "x")
        self.assertEqual(code, 1)
        self.assertIn("leads party", err)
        self.assertEqual(self.start("adv-1", "x")[0], 0)
        code, out, err = self.start("adv-1", "y")
        self.assertEqual(code, 1)
        self.assertIn("already an adventurer", err)

    def test_party_start_and_resume_refuse_an_adventurer(self):
        self.cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1")
        self.start("adv-1", "x")
        for argv in (["party", "start", "beta", "--reason", "test reason"], ["party", "resume", "alpha"]):
            code, out, err = self.cli(argv, "adv-1")
            self.assertEqual(code, 1, argv)
            self.assertIn("adventurer", err)

    def test_start_task_refusals(self):
        self.assertEqual(self.start("adv-1", "x", "--task", "demo-epic/T99")[0], 1)
        self.assertEqual(self.start("adv-1", "x", "--task", "bad")[0], 1)
        self.cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1")
        self.cli(["quest", "add", "qa", "--title", "qa", "--epic", "demo-epic", "--tasks", "T01"], "sess-1")
        code, out, err = self.start("adv-1", "x", "--task", "demo-epic/T01")
        self.assertEqual(code, 1)
        self.assertIn("quest qa", err)
        self.cli(["claim", "task:demo-epic/T03", "--ttl", "2h"], "sess-1")
        code, out, err = self.start("adv-1", "x", "--task", "demo-epic/T03")
        self.assertEqual(code, 1)
        self.assertIn("claimed by party alpha", err)
        self.assertEqual(self.start("adv-1", "x", "--task", "demo-epic/T02")[0], 0)
        code, out, err = self.start("adv-2", "y", "--task", "demo-epic/T02")
        self.assertEqual(code, 1)
        self.assertIn("held by adventurer 1", err)

    def test_done_requires_pending(self):
        self.start("adv-1", "x")
        code, out, err = self.cli(["adventurer", "done"], "adv-1")
        self.assertEqual(code, 2)
        self.assertEqual(self.rows("SELECT state FROM adventurers")[0]["state"], "active")

    def test_done_none_is_accepted_and_ends_the_adventurer(self):
        self.start("adv-1", "x")
        code, out, err = self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        self.assertEqual(code, 0, err)
        row = self.rows("SELECT state, pending, done_at FROM adventurers")[0]
        self.assertEqual((row["state"], row["pending"]), ("done", "none"))
        self.assertIsNotNone(row["done_at"])
        self.assertEqual(self.cli(["adventurer", "done", "--pending", "none"], "adv-1")[0], 1)
        code, out, err = self.cli(["adventurers"], None)
        self.assertIn("done", out)

    def test_done_validates_pending_text(self):
        self.start("adv-1", "x")
        self.assertEqual(self.cli(["adventurer", "done", "--pending", " "], "adv-1")[0], 1)
        self.assertEqual(self.cli(["adventurer", "done", "--pending", "ping me@x.com"], "adv-1")[0], 1)
        self.assertEqual(self.cli(["adventurer", "done", "--pending", "x"], "other")[0], 1)

    def test_done_frees_the_task_and_the_session_can_start_again(self):
        self.start("adv-1", "x", "--task", "demo-epic/T02")
        self.cli(["adventurer", "done", "--pending", "left the tests"], "adv-1")
        self.assertEqual(self.start("adv-2", "y", "--task", "demo-epic/T02")[0], 0)
        self.assertEqual(self.start("adv-1", "z")[0], 0)

    def test_state_survives_rebuild(self):
        self.start("adv-1", "x", "--task", "demo-epic/T02")
        self.start("adv-2", "y")
        self.cli(["adventurer", "done", "--pending", "none"], "adv-2")
        code, out, err = self.cli(["rebuild"], None)
        self.assertEqual(code, 0, err)
        rows = self.rows("SELECT id, session_id, task, state, pending FROM adventurers ORDER BY id")
        self.assertEqual([(r["id"], r["task"], r["state"], r["pending"]) for r in rows],
                         [(1, "demo-epic/T02", "active", None), (2, None, "done", "none")])


class AdventurerHoldsTaskTests(AdventurerTestCase):
    def setUp(self):
        super().setUp()
        self.cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1")
        self.start("adv-1", "x", "--task", "demo-epic/T02")

    def test_quest_add_skips_the_held_task(self):
        code, out, err = self.cli(
            ["quest", "add", "qa", "--title", "qa", "--epic", "demo-epic", "--tasks", "T02"], "sess-1"
        )
        self.assertEqual(code, 1)
        self.assertIn("T02 is held by adventurer 1", err)

    def test_task_add_skips_the_held_task(self):
        self.cli(["quest", "add", "qa", "--title", "qa", "--epic", "demo-epic"], "sess-1")
        code, out, err = self.cli(["task", "add", "qa/T02", "--title", "t"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("held by adventurer 1", err)

    def test_claim_check_and_claim_see_the_holder(self):
        code, out, err = self.cli(["claim", "check", "task:demo-epic/T02"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("held by adventurer 1", out)
        code, out, err = self.cli(["claim", "task:demo-epic/T02", "--ttl", "2h"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("held by adventurer 1", err)

    def test_done_releases_the_task_for_quests(self):
        self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        code, out, err = self.cli(
            ["quest", "add", "qa", "--title", "qa", "--epic", "demo-epic", "--tasks", "T02"], "sess-1"
        )
        self.assertEqual(code, 0, err)


class AdventurerPermissionTests(AdventurerTestCase):
    def setUp(self):
        super().setUp()
        self.start("adv-1", "x", "--task", "demo-epic/T02")
        self.write_gh_fixture("view_acme-app_1", dict(OPEN_VIEW))
        self.write_gh_fixture("view_acme-app_2", dict(OPEN_VIEW))

    def test_party_commands_refuse_with_the_adventurer_message(self):
        for argv in (
            ["quest", "add", "q", "--title", "q", "--no-epic"],
            ["claim", "area:x", "--ttl", "1h"],
            ["handoff", "--in-flight", "a", "--learned", "b"],
            ["next"],
        ):
            code, out, err = self.cli(argv, "adv-1")
            self.assertEqual(code, 1, argv)
            self.assertIn("adventurers do one job", err, argv)
            self.assertNotIn("session not bound", err, argv)

    def test_pr_track_on_a_task_accepts_only_its_own_task(self):
        code, out, err = self.cli(["pr", "track", "acme/app#1", "--card", "ABC-1", "--what", "w", "--waits", "r"], "adv-1")
        self.assertEqual(code, 1)
        self.assertIn("--task equal to its own task", err)
        code, out, err = self.cli(["pr", "track", "acme/app#3", "--task", "demo-epic/T01", "--what", "w", "--waits", "r"], "adv-1")
        self.assertEqual(code, 1)
        code, out, err = self.cli(["pr", "track", "acme/app#2", "--task", "demo-epic/T02", "--what", "w", "--waits", "r"], "adv-1")
        self.assertEqual(code, 0, err)
        row = self.rows("SELECT party, adventurer, task_quest FROM prs WHERE number = 2")[0]
        self.assertEqual((row["party"], row["adventurer"], row["task_quest"]), ("", 1, None))

    def test_done_prints_final_report(self):
        self.start("adv-1", "fix typo", "--task", "demo-epic/T02")
        self.cli(["pr", "track", "acme/app#2", "--task", "demo-epic/T02", "--what", "fixes typo", "--waits", "r"], "adv-1")
        code, out, err = self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        self.assertEqual(code, 0, err)
        self.assertIn("adventurer 1 done", out)
        self.assertIn("final report for adventurer 1", out)
        self.assertIn("job: x", out)
        self.assertIn("task: demo-epic/T02", out)
        self.assertIn("acme/app#2 | fixes typo | open", out)
        self.assertIn("pending: none", out)

    def test_done_refreshes_a_stale_pr_to_merged(self):
        self.start("adv-1", "fix typo", "--task", "demo-epic/T02")
        self.cli(["pr", "track", "acme/app#2", "--task", "demo-epic/T02", "--what", "fixes typo", "--waits", "r"], "adv-1")
        self.write_gh_fixture("view_acme-app_2", dict(OPEN_VIEW, state="MERGED", mergedAt="2026-01-01T00:00:00Z"))
        code, out, err = self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        self.assertEqual(code, 0, err)
        self.assertIn("acme/app#2 | fixes typo | merged", out)
        self.assertNotIn("as of last sync", out)

    def test_done_notes_the_last_sync_when_gh_fails(self):
        self.start("adv-1", "fix typo", "--task", "demo-epic/T02")
        self.cli(["pr", "track", "acme/app#2", "--task", "demo-epic/T02", "--what", "fixes typo", "--waits", "r"], "adv-1")
        self.write_gh_error("view_acme-app_2", "boom")
        code, out, err = self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        self.assertEqual(code, 0, err)
        self.assertIn("acme/app#2 | fixes typo | open", out)
        self.assertIn("(PR state as of last sync)", out)

    def test_pr_track_on_a_free_job_refuses_a_task(self):
        self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        self.start("adv-2", "free job")
        code, out, err = self.cli(["pr", "track", "acme/app#1", "--task", "demo-epic/T02", "--what", "w", "--waits", "r"], "adv-2")
        self.assertEqual(code, 1)
        self.assertIn("without --task", err)
        code, out, err = self.cli(["pr", "track", "acme/app#1", "--card", "ABC-1", "--what", "w", "--waits", "r"], "adv-2")
        self.assertEqual(code, 0, err)

    def test_pr_track_on_a_free_job_needs_no_card(self):
        self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        self.start("adv-2", "free job")
        code, out, err = self.cli(["pr", "track", "acme/app#1", "--what", "fixes typo", "--waits", "r"], "adv-2")
        self.assertEqual(code, 0, err)
        code, out, err = self.cli(["adventurer", "done", "--pending", "none"], "adv-2")
        self.assertEqual(code, 0, err)
        self.assertIn("acme/app#1 | fixes typo", out)

    def test_adventurer_prs_do_not_break_party_views(self):
        self.cli(["pr", "track", "acme/app#2", "--task", "demo-epic/T02", "--what", "w", "--waits", "r"], "adv-1")
        self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        self.start("adv-2", "free job")
        self.cli(["pr", "track", "acme/app#1", "--card", "ABC-1", "--what", "w", "--waits", "r"], "adv-2")
        self.cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1")
        code, out, err = self.cli(["sync", "--source", "gh"], None)
        self.assertEqual(code, 0, err)
        for argv, session in (
            (["board"], None),
            (["board"], "sess-1"),
            (["next"], "sess-1"),
            (["merge-queue"], "sess-1"),
            (["merge-queue", "--party", "alpha"], None),
            (["merge-queue", "--head"], "sess-1"),
            (["pr", "ready-check", "acme/app#2"], None),
            (["pr", "ready-check", "acme/app#1"], "sess-1"),
            (["history"], None),
            (["brief"], "sess-1"),
            (["drift"], None),
        ):
            code, out, err = self.cli(argv, session)
            self.assertEqual(code, 0, (argv, err))

    def test_notice_idea_and_ask_carry_the_adventurer_label(self):
        code, out, err = self.cli(["notice", "create", "heads up", "--to", "project:acme", "--ttl", "1h"], "adv-1")
        self.assertEqual(code, 0, err)
        code, out, err = self.cli(["idea", "add", "an idea", "--description", "d"], "adv-1")
        self.assertEqual(code, 0, err)
        code, out, err = self.cli(["ask", "q?", "--context", "c", "--ref", "task:demo-epic/T02"], "adv-1")
        self.assertEqual(code, 0, err)
        code, out, err = self.cli(["notices"], None)
        self.assertIn("adventurer 1", out)
        self.assertEqual(self.rows("SELECT party FROM asks")[0]["party"], "adventurer 1")
        self.assertEqual(self.rows("SELECT party FROM events WHERE kind = 'idea.created'")[0]["party"], "adventurer 1")


class AdventurerHookTests(AdventurerTestCase):
    def payload(self, session_id):
        return {"session_id": session_id, "cwd": str(self.repo_dir)}

    def status(self, session_id):
        rows = self.rows("SELECT status, party FROM session_status WHERE session_id = '{}'".format(session_id))
        return None if not rows else (rows[0]["status"], rows[0]["party"])

    def test_stop_records_once_for_an_adventurer(self):
        self.start("adv-1", "x")
        code, out, err = self.run_hook("stop", self.payload("adv-1"))
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(self.status("adv-1"), ("stopped", ""))
        self.run_hook("stop", self.payload("adv-1"))
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM events WHERE kind = 'session.stopped'")[0]["n"], 1)

    def test_stop_ignores_an_ended_adventurer(self):
        self.start("adv-1", "x")
        self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        self.run_hook("stop", self.payload("adv-1"))
        self.assertIsNone(self.status("adv-1"))

    def test_prompt_after_stop_marks_working_and_no_unbound_hint(self):
        self.start("adv-1", "x")
        self.run_hook("stop", self.payload("adv-1"))
        code, out, err = self.run_hook("prompt-submit", self.payload("adv-1"))
        self.assertNotIn("session not bound", out)
        self.assertEqual(self.status("adv-1"), ("working", ""))

    def test_unbound_hint_asks_party_or_adventurer(self):
        code, out, err = self.run_hook("prompt-submit", self.payload("sess-9"))
        self.assertIn("session not bound", out)
        self.assertIn("guild adventurer start", out)
        self.assertIn("guild party start", out)

    def test_brief_of_an_adventurer_names_its_job(self):
        self.start("adv-1", "fix typo", "--task", "demo-epic/T02")
        code, out, err = self.cli(["brief"], "adv-1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("session not bound", out)
        self.assertIn("adventurer 1", out)
        self.assertIn("fix typo", out)
