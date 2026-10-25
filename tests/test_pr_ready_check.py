import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from guild import merge_queue as merge_queue_model
from guild.commands import merge_queue
from tests.lifecycle_fixtures import init_clone
from tests.mq_fixtures import OPEN_VIEW, TASKS_MD, MergeQueueTestCase


class ReadyCheckTests(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        self.start_party("alpha", "sess-1")
        code, out, err = self.sync_sdd(self.repo_dir, "sess-1", "acme", "demo-epic", TASKS_MD)
        self.assertEqual(code, 0, err)
        self.add_quest("sess-1", "qa", "demo-epic", "T01,T02,T03")

    def check(self, number):
        return self.run_cli(["pr", "ready-check", "acme/app#{}".format(number)], "sess-1", self.repo_dir)

    def test_ready_pr_exits_zero(self):
        self.track("sess-1", 3, "qa/T03", "ready")
        self.sync_gh("sess-1")
        code, out, err = self.check(3)
        self.assertEqual((code, out), (0, "acme/app#3 ready\n"))

    def test_main_blocked_by_billing_exits_zero(self):
        self.mark_billing_blocked()
        self.track("sess-1", 3, "qa/T03", "ready")
        self.sync_gh("sess-1")
        code, out, err = self.check(3)
        self.assertEqual((code, out), (0, "acme/app#3 ready\n- note: main blocked: billing\n"))

    def test_lists_every_blocker(self):
        self.track("sess-1", 3, "qa/T03", "ready")
        self.write_gh_fixture(
            "view_acme-app_3", dict(OPEN_VIEW, mergeable="CONFLICTING", statusCheckRollup=[{"conclusion": "FAILURE"}])
        )
        self.sync_gh("sess-1")
        self.run_cli(["pr", "set", "acme/app#3", "--needs-ask-answer"], "sess-1", self.repo_dir)
        code, out, err = self.check(3)
        self.assertEqual(code, 1)
        self.assertEqual(
            out.splitlines(),
            ["acme/app#3 blocked", "- needs ask answer", "- checks failing (1)", "- merge conflict"],
        )

    def test_billing_blocked_checks_are_not_a_blocker(self):
        self.track("sess-1", 3, "qa/T03", "ready")
        self.write_gh_fixture(
            "view_acme-app_3", dict(OPEN_VIEW, statusCheckRollup=[{"conclusion": "FAILURE"}], headRefOid="head")
        )
        self.write_gh_fixture(
            "branch_checks_acme-app_head",
            {"check_runs": [{"id": 11, "name": "a", "conclusion": "failure", "output": {"annotations_count": 1}}]},
        )
        self.write_gh_fixture("annotations_acme-app_11", [{"message": "recent account payments have failed"}])
        self.sync_gh("sess-1")
        code, out, err = self.check(3)
        self.assertEqual((code, out), (0, "acme/app#3 ready (CI pending)\n- note: checks blocked by billing (1)\n"))

    def test_red_main_still_gates(self):
        self.track("sess-1", 3, "qa/T03", "ready")
        self.sync_gh("sess-1")
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.execute(
            "INSERT INTO main_status (repo, source, red, reason, external, updated_at)"
            " VALUES ('acme/app', 'gh', 1, 'boom', NULL, '2026-01-01T00:00:00Z')"
        )
        conn.commit()
        conn.close()
        code, out, err = self.check(3)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ["acme/app#3 ready", "- gate: main red acme/app \u2014 boom (gh)"])

    def test_comment_after_head_is_listed_as_missing(self):
        self.track("sess-1", 3, "qa/T03", "ready")
        self.write_gh_fixture(
            "view_acme-app_3",
            dict(
                OPEN_VIEW,
                author={"login": "me"},
                commits=[{"committedDate": "2026-10-20T10:00:00Z"}],
                comments=[{"author": {"login": "bot"}, "createdAt": "2026-10-20T11:00:00Z"}],
            ),
        )
        self.sync_gh("sess-1")
        code, out, err = self.check(3)
        self.assertEqual(code, 1)
        self.assertEqual(
            out.splitlines(),
            [
                "acme/app#3 blocked",
                "- 1 comment after head",
                "- gate: 1 review comment since last read (guild pr ack acme/app#3)",
            ],
        )

    def _comment_view(self, count):
        comments = [{"author": {"login": "bot"}, "createdAt": "2026-10-20T11:00:00Z"} for _ in range(count)]
        return dict(OPEN_VIEW, author={"login": "me"}, comments=comments)

    def test_unseen_comments_gate_then_ack_clears(self):
        self.track("sess-1", 3, "qa/T03", "ready")
        self.write_gh_fixture("view_acme-app_3", dict(OPEN_VIEW, commits=[{"committedDate": "2026-10-20T10:00:00Z"}]))
        self.sync_gh("sess-1")
        self.assertEqual(self.check(3)[:2], (0, "acme/app#3 ready\n"))
        view = dict(self._comment_view(2), commits=[{"committedDate": "2026-10-21T10:00:00Z"}])
        self.write_gh_fixture("view_acme-app_3", view)
        code, out, err = self.check(3)
        self.assertEqual(code, 1)
        self.assertIn("- gate: 2 review comments since last read (guild pr ack acme/app#3)", out.splitlines())
        code, out, err = self.run_cli(["pr", "ack", "acme/app#3"], "sess-1", self.repo_dir)
        self.assertEqual((code, out), (0, "PR 'acme/app#3' review comments marked as read\n"))
        self.assertEqual(self.check(3)[:2], (0, "acme/app#3 ready\n"))

    def test_new_comments_after_last_sync_are_found_by_the_refresh(self):
        self.track("sess-1", 3, "qa/T03", "ready")
        self.write_gh_fixture("view_acme-app_3", self._comment_view(0))
        self.sync_gh("sess-1")
        self.assertEqual(self.query("SELECT review_comment_count AS n FROM prs")[0]["n"], 0)
        self.write_gh_fixture("view_acme-app_3", self._comment_view(1))
        code, out, err = self.check(3)
        self.assertEqual(code, 1)
        self.assertIn("- gate: 1 review comment since last read (guild pr ack acme/app#3)", out.splitlines())

    def test_gh_failure_keeps_the_synced_state_with_a_note(self):
        self.track("sess-1", 3, "qa/T03", "ready")
        self.sync_gh("sess-1")
        self.write_gh_error("view_acme-app_3", "boom")
        code, out, err = self.check(3)
        self.assertEqual((code, out), (0, "acme/app#3 ready\n- note: state as of last sync\n"))

    def _configure_validator(self, code):
        init_clone(self.repo_dir, "acme/app")
        command = [sys.executable, "-I", "-c", code]
        self._set_project_config({"human_ready": {"trace_validator": {"command": command, "timeout_seconds": 30}}})

    def test_invalid_review_trace_is_listed_as_missing(self):
        self._configure_validator("print('no trace'); raise SystemExit(1)")
        self.track("sess-1", 3, "qa/T03", "ready")
        self.write_gh_fixture("view_acme-app_3", dict(OPEN_VIEW, headRefOid="d" * 40))
        self.sync_gh("sess-1")
        code, out, err = self.check(3)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ["acme/app#3 blocked", "- review trace invalid: no trace"])

    def test_unvalidated_review_trace_waits(self):
        init_clone(self.repo_dir, "acme/app")
        self._set_project_config(
            {"human_ready": {"trace_validator": {"command": ["/nonexistent/validator"], "timeout_seconds": 30}}}
        )
        self.track("sess-1", 3, "qa/T03", "ready")
        self.write_gh_fixture("view_acme-app_3", dict(OPEN_VIEW, headRefOid="d" * 40))
        self.sync_gh("sess-1")
        code, out, err = self.check(3)
        self.assertEqual(code, 1)
        self.assertEqual(
            out.splitlines(), ["acme/app#3 waiting", "- review trace not validated: validator could not start"]
        )

    def test_no_checks_without_label_config_waits(self):
        self.track("sess-1", 3, "qa/T03", "ready")
        self.write_gh_fixture("view_acme-app_3", dict(OPEN_VIEW, statusCheckRollup=[]))
        self.sync_gh("sess-1")
        code, out, err = self.check(3)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ["acme/app#3 waiting", "- no checks on head"])

    def test_no_checks_with_label_absent_is_ci_pending(self):
        self._set_project_config({"human_ready": {"ci_label": "run-ci"}})
        self.track("sess-1", 3, "qa/T03", "ready")
        self.write_gh_fixture("view_acme-app_3", dict(OPEN_VIEW, statusCheckRollup=[], labels=[]))
        self.sync_gh("sess-1")
        code, out, err = self.check(3)
        self.assertEqual((code, out), (0, "acme/app#3 ready (CI pending)\n- note: CI label run-ci not on the PR\n"))

    def test_shows_wait_on_predecessor(self):
        self.track("sess-1", 1, "qa/T01", "ready")
        self.track("sess-1", 2, "qa/T02", "draft")
        self.sync_gh("sess-1")
        code, out, err = self.check(1)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ["acme/app#1 blocked", "- waits on task T02", "- wait: waits on acme/app#2"])

    def test_successor_of_a_commented_predecessor_is_not_ready(self):
        self.track("sess-1", 2, "qa/T02", "ready")
        self.track("sess-1", 3, "qa/T03", "ready")
        self.write_gh_fixture(
            "view_acme-app_3",
            dict(
                OPEN_VIEW,
                author={"login": "me"},
                commits=[{"committedDate": "2026-10-20T10:00:00Z"}],
                comments=[{"author": {"login": "bot"}, "createdAt": "2026-10-20T11:00:00Z"}],
            ),
        )
        self.sync_gh("sess-1")
        code, out, err = self.run_cli(
            ["merge-queue", "pin", "acme/app#3", "--before", "acme/app#2"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.check(2)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ["acme/app#2 waiting", "- waits on acme/app#3"])

    def test_draft_gate_hints_promote_command(self):
        self.track("sess-1", 3, "qa/T03", "draft")
        code, out, err = self.check(3)
        self.assertEqual(code, 1)
        self.assertIn("- gate: draft (gh pr ready 3)", out.splitlines())
        self.assertEqual(out.splitlines()[0], "acme/app#3 waiting")

    def test_untracked_pr_errors(self):
        code, out, err = self.check(9)
        self.assertEqual(code, 1)
        self.assertIn("not tracked", err)


class ExternalReadyCheckTests(ReadyCheckTests):
    def test_external_block_fails_the_check_and_lists_the_reason(self):
        self.track("sess-1", 3, "qa/T03", "ready")
        self.sync_gh("sess-1")
        code, out, err = self.run_cli(
            ["pr", "set", "acme/app#3", "--blocked-external", "team meeting"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.check(3)
        self.assertEqual((code, out.splitlines()), (1, ["acme/app#3 blocked", "- manual block: team meeting"]))


def _entry(lifecycle, labels):
    return {
        "lifecycle": lifecycle,
        "labels": labels,
        "number": 7,
        "repo": "acme/app",
        "checks_billing": 0,
        "checks_failing": 0,
        "checks_passing": 0,
        "checks_pending": 0,
        "ci_label": None,
        "human_state": "ready",
        "unseen_comments": 0,
        "ref": "acme/app#7",
    }


class GatesTests(unittest.TestCase):
    def entry(self, lifecycle, labels):
        return _entry(lifecycle, labels)

    def test_ready_entry_has_no_gates(self):
        self.assertEqual(merge_queue.gates(self.entry("ready", []), []), [])

    def test_draft_and_converging_hint_the_promote_command(self):
        for lifecycle in ("draft", "converging"):
            self.assertEqual(merge_queue.gates(self.entry(lifecycle, []), []), ["draft (gh pr ready 7)"])

    def test_unseen_comments_gate_with_the_ack_hint(self):
        entry = dict(self.entry("ready", []), unseen_comments=2)
        self.assertEqual(merge_queue.gates(entry, []), ["2 review comments since last read (guild pr ack acme/app#7)"])
        entry = dict(entry, unseen_comments=1)
        self.assertEqual(merge_queue.gates(entry, []), ["1 review comment since last read (guild pr ack acme/app#7)"])

    def test_human_review_label_gates(self):
        self.assertEqual(merge_queue.gates(self.entry("ready", ["needs-human-pr-review"]), []), ["needs human review"])

    def test_billing_blocked_main_is_not_a_gate(self):
        rows = [{"repo": "acme/app", "reason": "boom", "source": "gh", "external": "billing"}]
        self.assertEqual(merge_queue.gates(self.entry("ready", []), rows), [])

    def test_only_red_main_of_the_same_repo_gates(self):
        rows = [
            {"repo": "acme/app", "reason": "boom", "source": "ci", "external": None},
            {"repo": "acme/other", "reason": "x", "source": "ci", "external": None},
        ]
        self.assertEqual(merge_queue.gates(self.entry("ready", []), rows), ["main red acme/app \u2014 boom (ci)"])


class NotesTests(unittest.TestCase):
    def entry(self, lifecycle, labels):
        return _entry(lifecycle, labels)

    def notes(self, entry, rows):
        with tempfile.TemporaryDirectory() as tmp:
            return merge_queue.notes(Path(tmp), entry, rows)

    def test_billing_main_of_the_same_repo_is_a_note(self):
        rows = [
            {"repo": "acme/app", "reason": "boom", "source": "gh", "external": "billing"},
            {"repo": "acme/other", "reason": "boom", "source": "gh", "external": "billing"},
        ]
        self.assertEqual(self.notes(self.entry("ready", []), rows), ["main blocked: billing"])

    def test_red_main_is_not_a_note(self):
        rows = [{"repo": "acme/app", "reason": "boom", "source": "gh", "external": None}]
        self.assertEqual(self.notes(self.entry("ready", []), rows), [])

    def test_billing_checks_are_a_note(self):
        entry = dict(self.entry("ready", []), checks_billing=1, checks_failing=2)
        self.assertEqual(self.notes(entry, []), ["checks blocked by billing (2)"])

    def write_project(self, tmp, human_ready):
        config = {"name": "acme", "paths": [tmp], "github": {"repos": ["acme/app"]}}
        if human_ready is not None:
            config["human_ready"] = human_ready
        (Path(tmp) / "acme.json").write_text(json.dumps(config))

    def ci_pending_entry(self):
        return dict(self.entry("ready", []), human_state=merge_queue_model.CI_PENDING_STATE, ci_label=0)

    def test_missing_label_note_is_skipped_when_checks_exist(self):
        entry = dict(self.ci_pending_entry(), checks_billing=1, checks_failing=2, checks_passing=0, checks_pending=0)
        self.assertEqual(self.notes(entry, []), ["checks blocked by billing (2)"])

    def test_missing_label_note_names_the_configured_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.write_project(tmp, {"ci_label": "run-ci"})
            self.assertEqual(
                merge_queue.notes(Path(tmp), self.ci_pending_entry(), []), ["CI label run-ci not on the PR"]
            )

    def test_missing_config_is_reported_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.write_project(tmp, None)
            self.assertEqual(
                merge_queue.notes(Path(tmp), self.ci_pending_entry(), []),
                ["CI label not on the PR (human_ready.ci_label no longer configured: run guild sync)"],
            )
