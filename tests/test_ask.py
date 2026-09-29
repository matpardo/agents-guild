import json
from datetime import timedelta

from guild import db, events, paths, timeutil
from guild.ids import next_id
from tests.testutil import GuildTestCase


class AskTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.conn = db.connect(paths.db_path())

    def _create_ask_event(self, party, question, ref_list, seconds_offset):
        ask_id = next_id(self.conn, "asks")
        moment = timeutil.utcnow() + timedelta(seconds=seconds_offset)
        with db.writing(self.conn):
            events.record(
                self.conn, moment, "test@host", party, None, "acme",
                "ask.created", "local",
                {
                    "id": ask_id, "party": party, "question": question, "context": "x",
                    "refs": ref_list, "options": [],
                },
            )
        return ask_id

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

    def test_create_requires_at_least_one_ref(self):
        code, out, err = self.run_cli(
            ["ask", "ready?", "--context", "x"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("at least one --ref", err)

    def test_create_rejects_unknown_task_ref(self):
        code, out, err = self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T99"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("does not match a known task", err)

    def test_create_and_list(self):
        code, out, err = self.run_cli(
            [
                "ask", "ready to merge?", "--context", "checks green",
                "--ref", "task:demo/T01", "--option", "yes", "--option", "no",
            ],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0)
        self.assertIn("ask #1 created", out)
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertIn("#1 alpha · ready to merge?", out)
        self.assertIn("options: yes | no", out)
        self.assertIn('guild answer 1 "..."', out)

    def test_answer_by_human(self):
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["answer", "1", "yes, go ahead"], None, None)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertIn("NEEDS YOU · nothing", out)

    def test_cannot_answer_twice(self):
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.run_cli(["answer", "1", "yes"], None, None)
        code, out, err = self.run_cli(["answer", "1", "again"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("not open", err)

    def test_dismiss(self):
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["dismiss", "1"], None, None)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertIn("NEEDS YOU · nothing", out)

    def test_asks_sorted_by_blocked_count_desc_then_created_then_id(self):
        self.run_cli(["task", "add", "demo/T02", "--title", "Second"], "sess-1", self.repo_dir)
        self.run_cli(
            ["ask", "single ref?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.run_cli(
            [
                "ask", "two refs?", "--context", "x",
                "--ref", "task:demo/T01", "--ref", "task:demo/T02",
            ],
            "sess-1", self.repo_dir,
        )
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertLess(out.index("two refs?"), out.index("single ref?"))

    def test_ordering_uses_blocked_count_not_raw_ref_count(self):
        self.run_cli(["task", "add", "demo/T02", "--title", "Second"], "sess-1", self.repo_dir)
        self.run_cli(["task", "done", "demo/T02"], "sess-1", self.repo_dir)
        self._create_ask_event("alpha", "one blocked ref?", ["task:demo/T01"], 0)
        self._create_ask_event(
            "alpha", "two refs but one done?", ["task:demo/T01", "task:demo/T02"], 1
        )
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertLess(out.index("one blocked ref?"), out.index("two refs but one done?"))

    def test_merged_pr_ref_no_longer_counts_as_blocked(self):
        self._track_pr(1, "demo", "T01")
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "pr:acme/app#1", "--ref", "task:demo/T01"],
            "sess-1", self.repo_dir,
        )
        self._set_pr_lifecycle(1, "merged")
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertIn("blocks: 1 of 2 refs still open", out)

    def test_done_task_ref_no_longer_counts_as_blocked(self):
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.run_cli(["task", "done", "demo/T01"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertIn("blocks: 0 of 1 refs still open (may be stale)", out)

    def test_untracked_pr_ref_counts_as_blocked(self):
        self._create_ask_event("alpha", "ghost pr?", ["pr:acme/app#99"], 0)
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertIn("blocks: 1 of 1 refs still open", out)

    def test_unknown_task_ref_counts_as_blocked(self):
        self._create_ask_event("alpha", "ghost task?", ["task:demo/T99"], 0)
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertIn("blocks: 1 of 1 refs still open", out)

    def test_asks_tie_break_by_id_when_blocked_count_and_created_at_match(self):
        moment = timeutil.utcnow()
        with db.writing(self.conn):
            for question, ask_id in (("first?", 1), ("second?", 2)):
                events.record(
                    self.conn, moment, "test@host", "alpha", None, "acme",
                    "ask.created", "local",
                    {
                        "id": ask_id, "party": "alpha", "question": question, "context": "x",
                        "refs": ["task:demo/T01"], "options": [],
                    },
                )
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertLess(out.index("first?"), out.index("second?"))

    def test_board_summary_shows_blocks_count(self):
        self.run_cli(["task", "add", "demo/T02", "--title", "Second"], "sess-1", self.repo_dir)
        self.run_cli(
            [
                "ask", "two refs?", "--context", "x",
                "--ref", "task:demo/T01", "--ref", "task:demo/T02",
            ],
            "sess-1", self.repo_dir,
        )
        code, out, err = self.run_cli(["board"], None, None)
        self.assertIn("· blocks 2", out)

    def test_board_summary_omits_blocks_when_zero(self):
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.run_cli(["task", "done", "demo/T01"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["board"], None, None)
        self.assertNotIn("blocks", out)

    def test_unknown_ask_id(self):
        code, out, err = self.run_cli(["answer", "42", "x"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("unknown ask", err)

    def test_create_prints_broadcast_reminder(self):
        code, out, err = self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0)
        self.assertIn("note: this text is broadcast to every session", out)

    def test_create_rejects_question_over_max_length(self):
        code, out, err = self.run_cli(
            ["ask", "x" * 301, "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("exceeds the maximum length", err)

    def test_create_rejects_context_over_max_length(self):
        code, out, err = self.run_cli(
            ["ask", "ready?", "--context", "x" * 2001, "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("exceeds the maximum length", err)

    def test_create_rejects_email_in_question(self):
        code, out, err = self.run_cli(
            ["ask", "reach jane.doe@example.com?", "--context", "x", "--ref", "task:demo/T01"],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("must not contain an email address", err)

    def test_answer_rejects_text_over_max_length(self):
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["answer", "1", "x" * 1001], None, None)
        self.assertEqual(code, 1)
        self.assertIn("exceeds the maximum length", err)

    def test_answer_rejects_email(self):
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["answer", "1", "ping jane.doe@example.com"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("must not contain an email address", err)


class AnswerPiiScopeTests(GuildTestCase):
    def test_answer_uses_the_asking_partys_project_patterns_from_any_directory(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data["pii_patterns"] = [r"\bID-\d{6}\b"]
        config_file.write_text(json.dumps(data))
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", repo_dir)
        self.run_cli(["ask", "who?", "--context", "c", "--ref", "task:demo/T01"], "sess-1", repo_dir)
        outside = self.root / "elsewhere"
        outside.mkdir()
        code, out, err = self.run_cli(["answer", "1", "it is ID-123456"], None, outside)
        self.assertEqual(code, 1)
        self.assertIn("answer", err)
        self.assertNotIn("ID-123456", err)


if __name__ == "__main__":
    import unittest

    unittest.main()
