
from guild import db, events, paths
from tests.mq_fixtures import OPEN_VIEW, TASKS_MD, MergeQueueTestCase, diff_fixture

_ES = "config/locales/es.yml"
_REMINDER = "guild never merges: merge in this order by hand; re-run after each merge"


def _view(passing, failing):
    rollup = [{"conclusion": "SUCCESS"}] * passing + [{"conclusion": "FAILURE"}] * failing
    return dict(OPEN_VIEW, statusCheckRollup=rollup)


class QueueCliTestCase(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        for name, session in (("alpha", "sess-1"), ("beta", "sess-2"), ("gamma", "sess-3"), ("delta", "sess-4")):
            self.start_party(name, session)
        code, out, err = self.sync_sdd(self.repo_dir, "sess-1", "acme", "demo-epic", TASKS_MD)
        self.assertEqual(code, 0, err)
        self.add_quest("sess-1", "qa", "demo-epic", "T01,T03")
        self.add_quest("sess-2", "qb", "demo-epic", "T02")
        for session, slug in (("sess-3", "qc"), ("sess-4", "qd")):
            self.run_cli(["quest", "add", slug, "--title", slug, "--no-epic"], session, self.repo_dir)
            self.run_cli(["task", "add", "{}/T01".format(slug), "--title", "t"], session, self.repo_dir)
        self.track("sess-1", 1, "qa/T01", "ready")
        self.track("sess-1", 3, "qa/T03", "ready")
        self.track("sess-2", 2, "qb/T02", "ready")
        self.track("sess-2", 4, "qb/T02", "ready")
        self.track("sess-3", 5, "qc/T01", "ready")
        self.track("sess-3", 6, "qc/T01", "draft")
        self.track("sess-4", 7, "qd/T01", "ready")
        self.run_cli(["raid", "join", "ci", "--until-leave", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-2", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-4", self.repo_dir)
        self.run_cli(["raid", "join", "other", "--until-leave"], "sess-4", self.repo_dir)
        self.write_gh_fixture("view_acme-app_1", _view(17, 0))
        self.write_gh_fixture("view_acme-app_4", _view(1, 2))
        self.write_gh_fixture("view_files_acme-app_1", diff_fixture([_ES], 40, 10, "2026-09-01T10:00:00Z"))
        self.write_gh_fixture("view_files_acme-app_2", diff_fixture([_ES], 5, 1, "2026-09-02T10:00:00Z"))
        self.write_gh_fixture("view_files_acme-app_3", diff_fixture(["src/a.py"], 1, 1, "2026-09-03T10:00:00Z"))
        self.write_gh_fixture("view_files_acme-app_4", diff_fixture(["src/b.py"], 1, 1, "2026-09-03T10:00:00Z"))
        self.write_gh_fixture("view_files_acme-app_7", diff_fixture(["src/c.py"], 1, 1, "2026-09-03T10:00:00Z"))
        code, out, err = self.sync_gh("sess-1")
        self.assertEqual(code, 0, err)

    def queue(self, argv, session_id):
        return self.run_cli(["merge-queue"] + argv, session_id, self.repo_dir)


class OutputTests(QueueCliTestCase):
    def test_raid_queue_lists_every_open_pr_in_order_with_its_action(self):
        code, out, err = self.queue(["--raid", "ci"], None)
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertEqual(lines[0], "merge queue \u00b7 raid ci \u00b7 synced 0 min ago")
        self.assertEqual(
            lines[1],
            "1. acme/app#2  beta  qb/T02  unblocks 1 \u2014 merge"
            " (ready, checks \u27131; before acme/app#1 (task T01 depends on T02))",
        )
        self.assertEqual(
            lines[2], "\u25b6 next action: 2. acme/app#4  beta  qb/T02  unblocks 1 \u2014 fix: checks failing (2) \u2192 beta"
        )
        self.assertEqual(
            lines[3],
            "3. acme/app#1  alpha  qa/T01  unblocks 1 \u2014 fix: waits on task T02; waits on acme/app#4 \u2192 alpha",
        )
        self.assertTrue(lines[4].startswith("4. acme/app#3  alpha  qa/T03  unblocks 0 \u2014 merge"))
        self.assertTrue(lines[5].startswith("5. acme/app#7  delta  qd/T01  unblocks 0 \u2014 merge"))

    def test_there_is_no_separate_blocked_section(self):
        code, out, err = self.queue(["--raid", "ci"], None)
        self.assertNotIn("blocked:", out)

    def test_red_main_shows_as_row_zero(self):
        code, out, err = self.run_cli(["main", "red", "acme/app", "--reason", "ci down"], None, self.repo_dir)
        self.assertEqual(code, 0, err)
        code, out, err = self.queue(["--raid", "ci"], None)
        self.assertEqual(
            out.splitlines()[1], "0. MAIN RED acme/app \u2014 ci down (manual) \u2192 fix before anything"
        )
        self.assertTrue(out.splitlines()[2].startswith("1. acme/app#2"))

    def test_footer_reminds_that_guild_never_merges(self):
        code, out, err = self.queue(["--raid", "ci"], None)
        self.assertEqual(out.splitlines()[-1], _REMINDER)

    def test_party_scope_lists_only_its_prs(self):
        code, out, err = self.queue(["--party", "gamma"], None)
        self.assertEqual(code, 0, err)
        self.assertIn("merge queue · party gamma", out)
        self.assertIn("1. acme/app#5  gamma  qc/T01  unblocks 0 \u2014 merge (ready, checks \u27131)", out)
        self.assertIn(
            "2. acme/app#6  gamma  qc/T01 [draft]  unblocks 0"
            " \u2014 promote: gh pr ready \u2192 gamma (ready, checks \u27131)",
            out,
        )
        self.assertNotIn("acme/app#1 ", out)

    def test_party_without_synced_data_says_never_synced(self):
        self.start_party("zeta", "sess-6")
        self.run_cli(["quest", "add", "qz", "--title", "qz", "--no-epic"], "sess-6", self.repo_dir)
        self.run_cli(["task", "add", "qz/T01", "--title", "t"], "sess-6", self.repo_dir)
        self.track("sess-6", 8, "qz/T01", "ready")
        code, out, err = self.queue(["--party", "zeta"], None)
        self.assertEqual(out.splitlines()[0], "merge queue \u00b7 party zeta \u00b7 never synced")

    def test_blocked_only_queue_keeps_every_row_with_a_fix_action(self):
        self.run_cli(["pr", "set", "acme/app#5", "--needs-ask-answer"], "sess-3", self.repo_dir)
        code, out, err = self.queue(["--party", "gamma"], None)
        self.assertIn("1. acme/app#5  gamma  qc/T01 [needs-ask-answer]  unblocks 0 \u2014 fix: needs ask answer \u2192 gamma", out)
        self.assertNotIn("next action", out)

    def test_pending_checks_show_a_wait_action(self):
        rollup = [{"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": ""}]
        self.write_gh_fixture("view_acme-app_5", dict(OPEN_VIEW, statusCheckRollup=rollup))
        self.write_gh_fixture("view_files_acme-app_5", diff_fixture(["src/d.py"], 1, 1, "2026-09-03T10:00:00Z"))
        code, out, err = self.sync_gh("sess-1")
        self.assertEqual(code, 0, err)
        code, out, err = self.queue(["--party", "gamma"], None)
        self.assertIn("1. acme/app#5  gamma  qc/T01  unblocks 0 \u2014 wait: checks pending (1)", out)
        self.assertIn("2. acme/app#6  gamma  qc/T01 [draft]", out)
        self.assertNotIn("next action", out)

    def test_review_flag_shows_a_human_review_action_and_its_label(self):
        self.run_cli(["pr", "set", "acme/app#5", "--needs-human-pr-review"], "sess-3", self.repo_dir)
        code, out, err = self.queue(["--party", "gamma"], None)
        self.assertIn("qc/T01 [needs-human-pr-review]", out)
        self.assertIn("review: human, then merge", out)

    def test_ask_flag_shows_its_label_after_the_draft_label(self):
        self.run_cli(["pr", "set", "acme/app#6", "--needs-ask-answer"], "sess-3", self.repo_dir)
        code, out, err = self.queue(["--party", "gamma"], None)
        self.assertIn("qc/T01 [draft] [needs-ask-answer]", out)

    def test_party_with_no_open_prs_says_so(self):
        self.run_cli(["party", "start", "epsilon"], "sess-5", self.repo_dir)
        code, out, err = self.queue(["--party", "epsilon"], None)
        self.assertEqual(code, 0, err)
        self.assertIn("no open tracked PRs", out)

    def test_pin_after_a_ready_draft_pr_makes_the_pinned_pr_wait(self):
        self.run_cli(["pr", "set", "acme/app#3", "--lifecycle", "draft"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            ["merge-queue", "pin", "acme/app#3", "--before", "acme/app#7"], None, self.repo_dir
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.queue(["--raid", "ci"], None)
        self.assertIn(
            "acme/app#3  alpha  qa/T03 [draft]  unblocks 1 \u2014 promote: gh pr ready \u2192 alpha", out
        )
        self.assertIn("acme/app#7  delta  qd/T01  unblocks 0 \u2014 wait: waits on acme/app#3", out)

    def test_pin_to_a_blocked_pr_keeps_it_first_with_a_fix_action(self):
        self.run_cli(["pr", "set", "acme/app#3", "--needs-ask-answer"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            ["merge-queue", "pin", "acme/app#3", "--before", "acme/app#7"], None, self.repo_dir
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.queue(["--raid", "ci"], None)
        self.assertIn("acme/app#3  alpha  qa/T03 [needs-ask-answer]  unblocks 1 \u2014 fix: needs ask answer \u2192 alpha", out)
        self.assertIn("acme/app#7  delta  qd/T01  unblocks 0 \u2014 fix: waits on acme/app#3 \u2192 delta", out)
        self.assertLess(out.index("acme/app#3  alpha"), out.index("acme/app#7  delta"))

    def test_pins_show_in_the_ready_entry_text(self):
        code, out, err = self.run_cli(
            ["merge-queue", "pin", "acme/app#3", "--before", "acme/app#7"], None, self.repo_dir
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.queue(["--raid", "ci"], None)
        self.assertIn("pinned before acme/app#7 by human", out)
        self.assertIn("pinned after acme/app#3 by human", out)

    def test_merged_pr_drops_out(self):
        self.write_gh_fixture(
            "view_acme-app_5",
            {
                "state": "MERGED", "isDraft": False, "headRefName": "f", "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z", "statusCheckRollup": [],
            },
        )
        self.sync_gh("sess-1")
        code, out, err = self.queue(["--party", "gamma"], None)
        self.assertNotIn("acme/app#5", out)


class ReadOnlyTests(QueueCliTestCase):
    def _max_seq(self):
        conn = db.connect(paths.db_path())
        try:
            return events.max_seq(conn)
        finally:
            conn.close()

    def test_makes_no_event_and_no_network_call(self):
        before = self._max_seq()
        for fixture in self.gh_fixtures_dir.iterdir():
            fixture.unlink()
        code, out, err = self.queue(["--raid", "ci"], None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._max_seq(), before)


class DefaultScopeTests(QueueCliTestCase):
    def test_bound_party_in_one_raid_uses_its_raid(self):
        code, out, err = self.queue([], "sess-2")
        self.assertEqual(code, 0, err)
        self.assertIn("raid ci", out.splitlines()[0])

    def test_bound_party_in_two_raids_is_an_error_listing_them(self):
        code, out, err = self.queue([], "sess-4")
        self.assertEqual(code, 1)
        self.assertIn("party 'delta' is in several raids: ci, other", err)
        self.assertIn("--raid", err)

    def test_bound_party_outside_raids_uses_its_party(self):
        code, out, err = self.queue([], "sess-3")
        self.assertEqual(code, 0, err)
        self.assertIn("party gamma", out.splitlines()[0])

    def test_human_terminal_requires_a_flag(self):
        code, out, err = self.queue([], None)
        self.assertEqual(code, 1)
        self.assertIn("--raid <name> or --party <name>", err)

    def test_unbound_session_requires_a_flag(self):
        code, out, err = self.queue([], "sess-unbound")
        self.assertEqual(code, 1)
        self.assertIn("--raid <name> or --party <name>", err)

    def test_raid_and_party_flags_are_mutually_exclusive(self):
        code, out, err = self.queue(["--raid", "ci", "--party", "alpha"], None)
        self.assertEqual(code, 2)
        self.assertIn("not allowed with argument", err)

    def test_unknown_raid_is_an_error(self):
        code, out, err = self.queue(["--raid", "nope"], None)
        self.assertEqual(code, 1)
        self.assertIn("raid 'nope' has no active members", err)

    def test_unknown_party_is_an_error(self):
        code, out, err = self.queue(["--party", "nope"], None)
        self.assertEqual(code, 1)
        self.assertIn("unknown party 'nope'", err)

    def test_explicit_flag_overrides_the_default(self):
        code, out, err = self.queue(["--party", "beta"], "sess-3")
        self.assertIn("party beta", out.splitlines()[0])


class BoardLineTests(QueueCliTestCase):
    def test_raid_board_starts_with_the_first_ready_pr_to_merge(self):
        code, out, err = self.run_cli(["board", "--raid", "ci"], None, self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], "next to merge: acme/app#2")

    def test_party_block_shows_its_next_pr_to_merge(self):
        code, out, err = self.run_cli(["board", "--party", "gamma"], None, self.repo_dir)
        self.assertIn("  next to merge: acme/app#5", out)

    def test_no_line_when_nothing_is_ready(self):
        self.run_cli(["pr", "set", "acme/app#5", "--lifecycle", "converging"], "sess-3", self.repo_dir)
        code, out, err = self.run_cli(["board", "--party", "gamma"], None, self.repo_dir)
        self.assertNotIn("next to merge", out)

    def test_plain_board_has_no_top_line_but_party_blocks_do(self):
        code, out, err = self.run_cli(["board"], None, self.repo_dir)
        self.assertFalse(out.splitlines()[0].startswith("next to merge"))
        self.assertIn("next to merge: acme/app#5", out)

    def test_raid_board_without_a_ready_pr_has_no_line(self):
        self.run_cli(["pr", "set", "acme/app#7", "--lifecycle", "converging"], "sess-4", self.repo_dir)
        code, out, err = self.run_cli(["board", "--raid", "other"], None, self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertNotIn("next to merge", out)

    def test_raid_board_shows_red_main_above_the_next_pr(self):
        self.run_cli(["main", "red", "acme/app", "--reason", "ci down"], None, self.repo_dir)
        code, out, err = self.run_cli(["board", "--raid", "ci"], None, self.repo_dir)
        lines = out.splitlines()
        self.assertEqual(lines[0], "MAIN RED: acme/app \u2014 ci down (manual)")
        self.assertEqual(lines[1], "next to merge: acme/app#2")

    def test_party_block_shows_red_main(self):
        self.run_cli(["main", "red", "acme/app", "--reason", "ci down"], None, self.repo_dir)
        code, out, err = self.run_cli(["board", "--party", "gamma"], None, self.repo_dir)
        self.assertIn("  MAIN RED: acme/app \u2014 ci down (manual)", out)


class SyncedLabelTests(QueueCliTestCase):
    def test_reports_minutes_since_the_latest_sync(self):
        from datetime import timedelta
        from unittest import mock

        from guild import timeutil

        later = timeutil.utcnow() + timedelta(minutes=12, seconds=30)
        with mock.patch("guild.timeutil.utcnow", return_value=later):
            code, out, err = self.queue(["--raid", "ci"], None)
        self.assertIn("synced 12 min ago", out.splitlines()[0])


if __name__ == "__main__":
    import unittest

    unittest.main()
