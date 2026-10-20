import json
import os
import sqlite3
import time

from guild import party_waits
from guild.cli import _build_context
from tests.mq_fixtures import MergeQueueTestCase, TASKS_MD
from tests.transcript_fixtures import write_transcript


def _limit_line(resets_at):
    return json.dumps(
        {
            "type": "assistant",
            "isApiErrorMessage": True,
            "error": "rate_limit",
            "apiErrorStatus": 429,
            "quotaLimits": {"status": "rejected", "resetsAt": resets_at, "rateLimitType": "five_hour"},
            "message": {"model": "<synthetic>", "content": [{"type": "text", "text": "limit"}]},
        }
    )


class PartyWaitsTests(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        self.start_party("alpha", "sess-1")
        code, out, err = self.sync_sdd(self.repo_dir, "sess-1", "acme", "demo-epic", TASKS_MD)
        self.assertEqual(code, 0, err)
        self.add_quest("sess-1", "qa", "demo-epic", "T01,T02,T03")
        self.track("sess-1", 1, "qa/T02", "ready")

    def update_pr(self, assignments):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.execute("UPDATE prs SET " + assignments + " WHERE number = 1")
        conn.commit()
        conn.close()

    def waits(self, party="alpha"):
        ctx = _build_context(None, self.repo_dir)
        try:
            row = ctx.conn.execute("SELECT * FROM parties WHERE name = ?", (party,)).fetchone()
            return [(wait["kind"], wait["subject"], wait["label"]) for wait in party_waits.for_party(ctx, row)]
        finally:
            ctx.conn.close()

    def kinds(self):
        return [kind for kind, subject, label in self.waits()]

    def test_green_ready_pr_waits_for_a_human_merge(self):
        self.update_pr("checks_pending = 0, checks_failing = 0, checks_passing = 1")
        self.assertEqual(self.waits(), [("human-merge", "acme/app#1", "merge")])

    def test_pending_checks(self):
        self.update_pr("checks_pending = 2")
        self.assertEqual(self.waits(), [("checks-pending", "acme/app#1", "checks pending (2)")])

    def test_failing_checks(self):
        self.update_pr("checks_failing = 1, checks_pending = 0")
        self.assertEqual(self.waits(), [("checks-failing", "acme/app#1", "checks failing (1)")])

    def test_failing_checks_with_real_classification_still_wait(self):
        self.update_pr("checks_failing = 1, checks_pending = 0, checks_billing = 0")
        self.assertEqual(self.kinds(), ["checks-failing"])

    def test_billing_failing_checks_make_no_wait_in_any_checked_lifecycle(self):
        self.update_pr("checks_failing = 1, checks_pending = 0, checks_billing = 1")
        for lifecycle in ("draft", "converging", "ready"):
            self.run_cli(["pr", "set", "acme/app#1", "--lifecycle", lifecycle], "sess-1", self.repo_dir)
            self.assertNotIn("checks-failing", self.kinds(), lifecycle)

    def test_draft_with_only_billing_failures_is_draft_green(self):
        self.run_cli(["pr", "set", "acme/app#1", "--lifecycle", "draft"], "sess-1", self.repo_dir)
        self.update_pr("checks_passing = 1, checks_failing = 1, checks_pending = 0, checks_billing = 1")
        self.assertEqual(self.waits(), [("draft-green", "acme/app#1", "green draft: mark ready")])

    def test_draft_with_real_failures_is_not_draft_green(self):
        self.run_cli(["pr", "set", "acme/app#1", "--lifecycle", "draft"], "sess-1", self.repo_dir)
        self.update_pr("checks_passing = 1, checks_failing = 1, checks_pending = 0, checks_billing = 0")
        self.assertEqual(self.kinds(), ["checks-failing"])

    def test_failing_checks_with_pending_report_pending_only(self):
        self.update_pr("checks_failing = 1, checks_pending = 1")
        self.assertEqual(self.kinds(), ["checks-pending"])

    def test_review_reasons(self):
        self.update_pr(
            "mergeable = 'CONFLICTING', review_decision = 'CHANGES_REQUESTED',"
            " unresolved_threads = 2, merge_state = 'BEHIND'"
        )
        self.assertEqual(self.kinds(), ["conflict", "changes-requested", "threads", "behind"])

    def test_human_review_flag(self):
        self.update_pr("needs_human_pr_review = 1")
        self.assertIn("human-review", self.kinds())

    def test_green_draft_waits_to_be_marked_ready(self):
        self.run_cli(["pr", "set", "acme/app#1", "--lifecycle", "draft"], "sess-1", self.repo_dir)
        self.update_pr("checks_passing = 1, checks_failing = 0, checks_pending = 0")
        self.assertEqual(self.waits(), [("draft-green", "acme/app#1", "green draft: mark ready")])

    def test_blocked_external_pr_is_not_a_merge_wait(self):
        self.update_pr("blocked_external = 'legal'")
        self.assertEqual(self.waits(), [])

    def test_open_ask(self):
        self.run_cli(["ask", "which one?", "--context", "c", "--ref", "card:PROJ-12"], "sess-1", self.repo_dir)
        self.assertIn(("ask-open", "ask #1", "ask #1 open"), self.waits())

    def test_answered_ask_waits_until_the_leader_reads_it(self):
        self.run_cli(["ask", "which one?", "--context", "c", "--ref", "card:PROJ-12"], "sess-1", self.repo_dir)
        self.run_cli(["answer", "1", "this one"], None, None)
        self.assertIn(("ask-answered-unseen", "ask #1", "ask #1 answered"), self.waits())
        self.run_cli(["inbox"], "sess-1", self.repo_dir)
        self.assertNotIn("ask-answered-unseen", self.kinds())

    def test_notice_from_another_party_is_unread_until_the_leader_reads_it(self):
        self.start_party("beta", "sess-2")
        self.run_cli(["notice", "create", "heads up", "--to", "project:acme", "--ttl", "1h"], "sess-2", self.repo_dir)
        self.assertIn(("notices-unread", "notice #1", "notice #1 unread"), self.waits())
        self.assertNotIn("notices-unread", [kind for kind, subject, label in self.waits("beta")])

    def test_unseen_waits_skip_events_of_other_kinds(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.execute(
            "INSERT INTO events (id, ts, origin, kind, visibility, payload)"
            " VALUES ('evt-x', '2026-10-14T00:00:00Z', 'test', 'other.kind', 'project', 'not json')"
        )
        conn.commit()
        conn.close()
        self.assertNotIn("notices-unread", self.kinds())

    def test_usage_limit_reset_of_a_live_leader(self):
        self.write_session(os.getpid(), "sess-1", "alpha")
        transcript = self.claude_projects_dir / "p" / "sess-1.jsonl"
        future = int(time.time()) + 3600
        write_transcript(transcript, [_limit_line(future)])
        kind, subject, label = [wait for wait in self.waits() if wait[0] == "limit-reset"][0]
        self.assertTrue(label.startswith("resets "))
        write_transcript(transcript, [_limit_line(int(time.time()) - 60)])
        self.assertIn(("limit-reset", "alpha", "reset: resume by hand"), self.waits())

    def test_closed_party_has_no_waits(self):
        self.update_pr("checks_pending = 2")
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.execute("UPDATE parties SET state = 'closed'")
        conn.commit()
        conn.close()
        self.assertEqual(self.waits(), [])
