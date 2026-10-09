import os
import json

from guild import context, ctx_pressure, db, paths, render, timeutil
from guild.commands import board as board_commands
from guild.commands import statusline as statusline_commands
from tests.testutil import GuildTestCase

_TASKS_MD = """---
epic: demo-epic
type: tasks
title: Demo Epic
status: active
updated: 2026-09-28
---

# Tasks

## T01 — First DEMO-1

**Deps:** —
**Status:** [ ] pending

## T02 — Second

**Deps:** —
**Status:** [ ] pending
"""


class BoardModelTestCase(GuildTestCase):
    def _ctx(self):
        conn = db.connect(paths.db_path())
        return context.RunContext(
            conn, None, None, timeutil.utcnow(), None,
            paths.claude_sessions_dir(), paths.projects_config_dir(), paths.state_dir(),
        )

    def _add_tracker_browse_url(self, project_name, browse_url):
        config_file = self.config_home / "guild" / "projects" / "{}.json".format(project_name)
        data = json.loads(config_file.read_text())
        data["tracker"] = {"browse_url": browse_url}
        config_file.write_text(json.dumps(data))


class BoardModelShapeTests(BoardModelTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self._add_tracker_browse_url("acme", "https://tracker.example/browse/")
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        code, out, err = self.sync_sdd(self.repo_dir, "sess-1", "acme", "demo-epic", _TASKS_MD)
        self.assertEqual(code, 0, err)
        self.run_cli(
            ["quest", "add", "demo", "--title", "Demo Quest", "--epic", "demo-epic", "--tasks", "T01,T02"],
            "sess-1", self.repo_dir,
        )
        self.run_cli(["task", "start", "demo/T01", "--summary", "in progress"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "Adds X", "--waits", "review"],
            "sess-1", self.repo_dir,
        )
        self.run_cli(
            ["ask", "Ship it?", "--context", "tests green", "--ref", "task:demo/T01",
             "--option", "yes", "--option", "no"],
            "sess-1", self.repo_dir,
        )
        self.run_cli(["notice", "create", "pipeline down", "--to", "guild", "--ttl", "2h"], None, None)
        self.run_cli(["claim", "src/x", "--ttl", "30m"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)

    def test_pr_model_carries_the_human_flags(self):
        self.run_cli(
            ["pr", "set", "acme/app#1", "--needs-ask-answer", "--needs-human-pr-review"],
            "sess-1", self.repo_dir,
        )
        ctx = self._ctx()
        model = board_commands.board_model(ctx)
        ctx.conn.close()
        tasks = {task["tid"]: task for task in model["parties"][0]["quests"][0]["tasks"]}
        pr = tasks["T01"]["prs"][0]
        self.assertEqual((pr["needs_ask_answer"], pr["needs_human_pr_review"]), (True, True))

    def test_party_model_carries_remaining_work(self):
        ctx = self._ctx()
        model = board_commands.board_model(ctx)
        ctx.conn.close()
        remaining = model["parties"][0]["remaining"]
        self.assertEqual(remaining["quests"], [{"slug": "demo", "done": 0, "total": 2}])
        self.assertEqual(
            (remaining["active"], remaining["blocked"], remaining["queued"], remaining["pending"]),
            (1, 0, 1, 2),
        )
        self.assertEqual(remaining["extra_prs"], 0)
        self.assertFalse(remaining["all_done"])

    def test_terminal_board_shows_the_flag_badges(self):
        self.run_cli(
            ["pr", "set", "acme/app#1", "--needs-ask-answer", "--needs-human-pr-review"],
            "sess-1", self.repo_dir,
        )
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("app#1  draft needs-ask-answer needs-human-pr-review  no checks", out)

    def _finish_pr(self, gh_fields):
        self.write_gh_fixture(
            "view_acme-app_1", dict({"headRefName": "feature/x", "title": "t"}, **gh_fields)
        )
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def _task_pr_model(self):
        ctx = self._ctx()
        model = board_commands.board_model(ctx)
        ctx.conn.close()
        tasks = {task["tid"]: task for task in model["parties"][0]["quests"][0]["tasks"]}
        return tasks["T01"]["prs"][0]

    def test_open_pr_keeps_its_waits_in_the_model_and_the_terminal_board(self):
        self.assertEqual(self._task_pr_model()["waits"], "review")
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("waits: review", out)

    def _clear_branch(self):
        conn = db.connect(paths.db_path())
        conn.execute("UPDATE prs SET branch = NULL")
        conn.commit()
        conn.close()

    def test_pr_model_exposes_its_branch_and_the_board_prints_it_dim_under_the_head(self):
        self.assertEqual(self._task_pr_model()["branch"], "feature/x")
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("branch: feature/x", out)

    def test_pr_without_a_branch_has_no_branch_in_the_model_and_no_branch_line(self):
        self._clear_branch()
        self.assertIsNone(self._task_pr_model()["branch"])
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertNotIn("branch:", out)

    def test_merged_pr_has_no_waits(self):
        self._finish_pr({"state": "MERGED", "isDraft": False, "mergedAt": "2026-09-01T10:00:00Z"})
        pr = self._task_pr_model()
        self.assertEqual((pr["lifecycle"], pr["waits"]), ("merged", None))
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("app#1  merged", out)
        self.assertNotIn("waits: review", out)

    def test_closed_pr_has_no_waits(self):
        self._finish_pr({"state": "CLOSED", "isDraft": False})
        pr = self._task_pr_model()
        self.assertEqual((pr["lifecycle"], pr["waits"]), ("closed", None))
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("app#1  closed", out)
        self.assertNotIn("waits: review", out)

    def test_brief_pr_line_drops_waits_for_a_merged_pr(self):
        self._finish_pr({"state": "MERGED", "isDraft": False, "mergedAt": "2026-09-01T10:00:00Z"})
        conn = db.connect(paths.db_path())
        row = conn.execute("SELECT * FROM prs WHERE number = 1").fetchone()
        conn.close()
        self.assertNotIn("waits", render.pr_line(row))

    def test_generated_at_is_iso(self):
        ctx = self._ctx()
        model = board_commands.board_model(ctx)
        ctx.conn.close()
        timeutil.from_iso(model["generated_at"])

    def test_ask_shape(self):
        ctx = self._ctx()
        model = board_commands.board_model(ctx)
        ctx.conn.close()
        self.assertEqual(len(model["asks"]), 1)
        ask = model["asks"][0]
        self.assertEqual(
            set(ask),
            {
                "id", "party", "question", "context", "options", "refs", "blocked", "total_refs",
                "created_at", "state", "answer", "answered_at",
            },
        )
        self.assertEqual((ask["state"], ask["answer"], ask["answered_at"]), ("open", None, None))
        self.assertEqual(ask["party"], "alpha")
        self.assertEqual(ask["question"], "Ship it?")
        self.assertEqual(ask["context"], "tests green")
        self.assertEqual(ask["options"], ["yes", "no"])
        self.assertEqual(ask["refs"], ["task:demo/T01"])
        self.assertEqual(ask["total_refs"], 1)
        self.assertEqual(ask["blocked"], 1)

    def test_asks_listed_in_ascending_id(self):
        self.run_cli(
            ["ask", "two refs?", "--context", "x", "--ref", "task:demo/T01", "--ref", "task:demo/T02"],
            "sess-1", self.repo_dir,
        )
        model = board_commands.board_model(self._ctx())
        ids = [ask["id"] for ask in model["asks"]]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), 2)

    def test_notice_shape(self):
        ctx = self._ctx()
        model = board_commands.board_model(ctx)
        ctx.conn.close()
        self.assertEqual(len(model["notices"]), 1)
        notice = model["notices"][0]
        self.assertEqual(set(notice), {"id", "party", "scope", "text", "issued_at", "issued", "expires_at", "time_left", "seen"})
        self.assertEqual(notice["time_left"], "1h left")
        self.assertIs(notice["seen"], False)
        self.assertEqual(notice["text"], "pipeline down")
        self.assertEqual(notice["scope"], "guild")

    def test_party_and_quest_and_task_shape(self):
        ctx = self._ctx()
        model = board_commands.board_model(ctx)
        ctx.conn.close()
        self.assertEqual(len(model["parties"]), 1)
        party = model["parties"][0]
        self.assertEqual(
            set(party),
            {
                "name", "state", "generation", "status", "ctx", "resume_command",
                "leader_session_name", "quests", "prs", "raids", "claims", "remaining",
            },
        )
        self.assertEqual(party["name"], "alpha")
        self.assertEqual(party["state"], "active")
        self.assertEqual(len(party["quests"]), 1)
        quest = party["quests"][0]
        self.assertEqual(set(quest), {"slug", "title", "tasks"})
        self.assertEqual(quest["slug"], "demo")
        tasks_by_tid = {task["tid"]: task for task in quest["tasks"]}
        self.assertEqual(set(tasks_by_tid), {"T01", "T02"})

        t01 = tasks_by_tid["T01"]
        self.assertEqual(
            set(t01),
            {"tid", "title", "state", "summary", "blocked_reason", "card_url", "prs"},
        )
        self.assertEqual(t01["state"], "active")
        self.assertEqual(t01["summary"], "in progress")
        self.assertIsNone(t01["blocked_reason"])
        self.assertEqual(t01["card_url"], "https://tracker.example/browse/DEMO-1")
        self.assertEqual(len(t01["prs"]), 1)
        pr = t01["prs"][0]
        self.assertEqual(
            set(pr),
            {
                "repo", "number", "lifecycle", "needs_ask_answer", "needs_human_pr_review", "checks_failing",
                "checks_passing", "checks_pending", "what", "waits", "url", "card", "card_url",
                "branch", "fixes_main", "fixes_flaky",
            },
        )
        self.assertEqual(pr["repo"], "acme/app")
        self.assertEqual(pr["number"], 1)
        self.assertEqual((pr["needs_ask_answer"], pr["needs_human_pr_review"]), (False, False))
        self.assertEqual((pr["branch"], pr["fixes_main"], pr["fixes_flaky"]), ("feature/x", False, False))
        self.assertEqual(pr["what"], "Adds X")
        self.assertEqual(pr["url"], "https://github.com/acme/app/pull/1")

        t02 = tasks_by_tid["T02"]
        self.assertEqual(t02["state"], "queued")
        self.assertIsNone(t02["card_url"])
        self.assertEqual(t02["prs"], [])

        self.assertEqual(party["prs"], [])
        self.assertEqual(len(party["claims"]), 1)
        self.assertEqual(party["claims"][0]["area"], "src/x")
        self.assertEqual(len(party["raids"]), 1)
        self.assertEqual(party["raids"][0]["raid"], "ci")
        self.assertEqual(set(party["raids"][0]), {"raid", "expires_at", "lead", "paused"})
        self.assertFalse(party["raids"][0]["lead"])

    def test_drift_shape_for_projects_in_scope(self):
        ctx = self._ctx()
        model = board_commands.board_model(ctx)
        ctx.conn.close()
        self.assertEqual(len(model["drift"]), 1)
        entry = model["drift"][0]
        self.assertEqual(set(entry), {"project", "scope", "findings"})
        self.assertEqual(entry["project"], "acme")
        self.assertTrue(entry["scope"].startswith("scope:"))
        self.assertIsInstance(entry["findings"], dict)


class BoardModelRaidsTests(BoardModelTestCase):
    def test_raids_model_lists_name_lead_and_members(self):
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-2", self.repo_dir)

        ctx = self._ctx()
        model = board_commands.board_model(ctx)
        ctx.conn.close()

        self.assertEqual(len(model["raids"]), 1)
        raid = model["raids"][0]
        self.assertEqual(set(raid), {"name", "lead", "members", "paused"})
        self.assertEqual(raid["name"], "ci")
        self.assertEqual(raid["lead"], "alpha")
        self.assertEqual(set(raid["members"]), {"alpha", "beta"})

    def test_raids_model_has_no_lead_when_none_joined_as_lead(self):
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)

        ctx = self._ctx()
        model = board_commands.board_model(ctx)
        ctx.conn.close()

        self.assertIsNone(model["raids"][0]["lead"])

    def test_raids_model_empty_when_no_raids(self):
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

        ctx = self._ctx()
        model = board_commands.board_model(ctx)
        ctx.conn.close()

        self.assertEqual(model["raids"], [])


class BoardModelPartyWithoutProjectTests(BoardModelTestCase):
    def test_party_without_project_is_skipped_from_drift(self):
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "gamma"], "sess-2", None)

        ctx = self._ctx()
        model = board_commands.board_model(ctx)
        ctx.conn.close()

        self.assertEqual({party["name"] for party in model["parties"]}, {"alpha", "gamma"})
        self.assertEqual([entry["project"] for entry in model["drift"]], ["acme"])


class BoardModelSeenNoticeTests(BoardModelTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["notice", "create", "pipeline down", "--to", "guild", "--ttl", "5h"], None, None)
        self.run_cli(["notice", "create", "ci flaky", "--to", "guild", "--ttl", "2h"], None, None)

    def _model(self):
        ctx = self._ctx()
        try:
            return board_commands.board_model(ctx)
        finally:
            ctx.conn.close()

    def test_new_notice_count_and_seen_flags_reflect_the_mark(self):
        self.run_cli(["notice", "seen", "1"], None, None)
        model = self._model()
        self.assertEqual([(n["id"], n["seen"]) for n in model["notices"]], [(2, False), (1, True)])
        self.assertEqual(model["new_notice_count"], 1)

    def test_every_notice_stays_listed_when_seen(self):
        self.run_cli(["notice", "seen", "--all"], None, None)
        model = self._model()
        self.assertEqual(len(model["notices"]), 2)
        self.assertEqual(model["new_notice_count"], 0)

    def test_unseen_notices_count_as_new(self):
        self.assertEqual(self._model()["new_notice_count"], 2)


if __name__ == "__main__":
    import unittest

    unittest.main()


class BoardModelCtxPressureTests(BoardModelTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.write_session(os.getpid(), "sess-1", "alpha-g1")

    def _party(self):
        ctx = self._ctx()
        model = board_commands.board_model(ctx)
        ctx.conn.close()
        return model["parties"][0]

    def test_ctx_is_null_without_a_recorded_pct(self):
        self.assertIsNone(self._party()["ctx"])

    def test_ctx_is_null_below_the_threshold(self):
        statusline_commands.record_ctx(
            paths.state_dir(), "sess-1", ctx_pressure.DEFAULT_HANDOFF_THRESHOLD - 1
        )
        self.assertIsNone(self._party()["ctx"])

    def test_ctx_carries_pct_and_threshold_when_high(self):
        statusline_commands.record_ctx(paths.state_dir(), "sess-1", 93)
        self.assertEqual(
            self._party()["ctx"],
            {"pct": 93, "threshold": ctx_pressure.DEFAULT_HANDOFF_THRESHOLD, "high": True},
        )

    def test_ctx_is_null_when_the_leader_session_is_gone(self):
        statusline_commands.record_ctx(paths.state_dir(), "sess-1", 93)
        (self.sessions_dir / "{}.json".format(os.getpid())).unlink()
        self.assertIsNone(self._party()["ctx"])

    def test_resume_command_is_null_while_active(self):
        self.assertIsNone(self._party()["resume_command"])

    def test_resume_command_is_set_after_a_handoff(self):
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.run_cli(
            ["handoff", "--in-flight", "wiring the board", "--learned", "nothing new"],
            "sess-1",
            self.repo_dir,
        )
        command = self._party()["resume_command"]
        self.assertIn("GUILD_RESUME=alpha", command)
        self.assertIn("alpha-g2", command)
        self.assertIn(str(self.repo_dir), command)


class BoardModelSessionStatusTests(BoardModelTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.write_session(os.getpid(), "sess-1", "alpha-g1")

    def _model(self):
        ctx = self._ctx()
        model = board_commands.board_model(ctx)
        ctx.conn.close()
        return model

    def _notify(self, notification_type, message):
        self.run_hook(
            "notification",
            {
                "session_id": "sess-1",
                "cwd": str(self.repo_dir),
                "notification_type": notification_type,
                "message": message,
            },
        )

    def test_party_status_without_session_row_is_unknown(self):
        status = self._model()["parties"][0]["status"]
        self.assertEqual(status, {"name": "unknown", "since": None, "detail": None, "label": "unknown"})

    def test_party_status_without_live_session_is_idle(self):
        (self.sessions_dir / "{}.json".format(os.getpid())).unlink()
        status = self._model()["parties"][0]["status"]
        self.assertEqual(status, {"name": "idle", "since": None, "detail": None, "label": "idle"})

    def test_party_status_waiting_permission_and_blocked_list(self):
        self._notify("permission_prompt", "run ls")
        model = self._model()
        status = model["parties"][0]["status"]
        self.assertEqual(status["name"], "waiting-permission")
        self.assertEqual(status["detail"], "run ls")
        self.assertRegex(status["label"], r"^waiting-permission \d+s$")
        self.assertEqual(len(model["blocked"]), 1)
        blocked = model["blocked"][0]
        self.assertEqual((blocked["party"], blocked["wait"], blocked["detail"]), ("alpha", "permission", "run ls"))
        self.assertEqual(blocked["since"], status["since"])
        self.assertEqual(blocked["label"], status["label"])

    def test_blocked_empty_when_not_waiting_on_permission(self):
        self._notify("idle_prompt", "idle")
        self.assertEqual(self._model()["blocked"], [])

    def test_status_and_blocked_detail_sanitized(self):
        self._notify("permission_prompt", "a\x1b[31mb")
        model = self._model()
        self.assertNotIn("\x1b", json.dumps(model))
