import json

from guild import context, db, paths, timeutil
from guild.commands import board as board_commands
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
            paths.claude_sessions_dir(), paths.projects_config_dir(), None,
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
            {"id", "party", "question", "context", "options", "refs", "blocked", "total_refs", "created_at"},
        )
        self.assertEqual(ask["party"], "alpha")
        self.assertEqual(ask["question"], "Ship it?")
        self.assertEqual(ask["context"], "tests green")
        self.assertEqual(ask["options"], ["yes", "no"])
        self.assertEqual(ask["refs"], ["task:demo/T01"])
        self.assertEqual(ask["total_refs"], 1)
        self.assertEqual(ask["blocked"], 1)

    def test_notice_shape(self):
        ctx = self._ctx()
        model = board_commands.board_model(ctx)
        ctx.conn.close()
        self.assertEqual(len(model["notices"]), 1)
        notice = model["notices"][0]
        self.assertEqual(set(notice), {"id", "party", "scope", "text", "expires_at"})
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
            {"name", "state", "generation", "leader_session_name", "quests", "prs", "raids", "claims"},
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
            {"repo", "number", "lifecycle", "checks_failing", "checks_passing", "what", "waits", "url"},
        )
        self.assertEqual(pr["repo"], "acme/app")
        self.assertEqual(pr["number"], 1)
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


if __name__ == "__main__":
    import unittest

    unittest.main()
