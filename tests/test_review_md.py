import re

from tests.mq_fixtures import OPEN_VIEW, MergeQueueTestCase

_FORBIDDEN_RE = re.compile(r"guild|party|raid|quest|ask #[0-9]|notice #[0-9]", re.IGNORECASE)
_PENDING = [{"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": ""}]
_REF_RE = re.compile(r"^- \[ \] (\S+)", re.MULTILINE)
_QUEUE_REF_RE = re.compile(r"^(?:▶ next action: )?\d+\. (\S+)", re.MULTILINE)


class ReviewMdTestCase(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        self.start_party("alpha", "sess-1")
        self.start_party("beta", "sess-2")
        for session, slug in (("sess-1", "qa"), ("sess-2", "qb")):
            self.run_cli(["quest", "add", slug, "--title", slug, "--no-epic"], session, self.repo_dir)
            for tid in ("T01", "T02", "T03", "T04", "T05", "T06"):
                self.run_cli(
                    ["task", "add", "{}/{}".format(slug, tid), "--title", tid, "--reason", "serves the goal"],
                    session,
                    self.repo_dir,
                )

    def track_ready(self, session, number, task, **view):
        self.track(session, number, task, "ready")
        self.write_gh_fixture("view_acme-app_{}".format(number), dict(OPEN_VIEW, **view))

    def review_md(self, argv):
        code, out, err = self.run_cli(["review-md"] + argv, "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        return out

    def refs(self, out):
        return _REF_RE.findall(out)


class SelectionTests(ReviewMdTestCase):
    def test_lists_only_human_ready_prs_of_the_scope(self):
        self.track_ready("sess-1", 1, "qa/T01")
        self.track("sess-1", 2, "qa/T02", "draft")
        self.track_ready("sess-1", 3, "qa/T03", statusCheckRollup=_PENDING)
        self.track_ready("sess-1", 4, "qa/T04")
        self.run_cli(["pr", "set", "acme/app#4", "--blocked-external", "vendor"], "sess-1", self.repo_dir)
        self.track_ready("sess-2", 5, "qb/T01")
        self.sync_gh("sess-1")
        self.assertEqual(self.refs(self.review_md([])), ["acme/app#1"])
        self.assertEqual(self.refs(self.review_md(["--party", "beta"])), ["acme/app#5"])

    def test_checks_pending_is_waiting_and_left_out(self):
        self.track_ready("sess-1", 1, "qa/T01", statusCheckRollup=_PENDING)
        self.sync_gh("sess-1")
        self.assertEqual(self.review_md([]), "Nothing is ready for you.\n")

    def test_ci_pending_pr_is_listed_with_its_note(self):
        self._set_project_config({"human_ready": {"ci_label": "run-ci"}})
        self.track_ready("sess-1", 1, "qa/T01", statusCheckRollup=[], labels=[])
        self.sync_gh("sess-1")
        out = self.review_md([])
        self.assertEqual(self.refs(out), ["acme/app#1"])
        self.assertIn("  - note: CI label run-ci not on the PR", out)

    def test_human_review_pr_is_listed_with_the_review_line(self):
        self.track_ready("sess-1", 1, "qa/T01")
        self.run_cli(["pr", "set", "acme/app#1", "--needs-human-pr-review"], "sess-1", self.repo_dir)
        self.sync_gh("sess-1")
        out = self.review_md([])
        self.assertEqual(self.refs(out), ["acme/app#1"])
        self.assertIn("  - review: human first", out)

    def test_red_main_empties_the_list_but_billing_main_does_not(self):
        self.track_ready("sess-1", 1, "qa/T01")
        self.sync_gh("sess-1")
        self.mark_billing_blocked()
        self.assertEqual(self.refs(self.review_md([])), ["acme/app#1"])
        self.run_cli(["main", "red", "acme/app", "--reason", "ci down"], None, self.repo_dir)
        self.assertEqual(self.refs(self.review_md([])), [])

    def test_empty_scope_prints_one_line_and_exits_zero(self):
        self.assertEqual(self.review_md([]), "Nothing is ready for you.\n")


class OutputTests(ReviewMdTestCase):
    def test_line_has_title_url_and_checks(self):
        self.track_ready("sess-1", 1, "qa/T01", title="Add thing")
        self.sync_gh("sess-1")
        self.assertEqual(
            self.review_md([]),
            "- [ ] acme/app#1 Add thing — https://github.com/acme/app/pull/1\n  - checks: 1 passing\n",
        )

    def test_title_is_one_line_without_control_sequences(self):
        self.track_ready("sess-1", 1, "qa/T01", title="Fix\n- [ ] acme/app#99 fake\x1b[31m red")
        self.sync_gh("sess-1")
        out = self.review_md([])
        self.assertEqual(self.refs(out), ["acme/app#1"])
        self.assertNotIn("\x1b", out)
        self.assertIn("acme/app#1 Fix - [ ] acme/app#99 fake red —", out)

    def test_output_has_no_forbidden_words(self):
        self.track_ready("sess-1", 1, "qa/T01")
        self.run_cli(["pr", "set", "acme/app#1", "--needs-human-pr-review"], "sess-1", self.repo_dir)
        self.sync_gh("sess-1")
        self.assertIsNone(_FORBIDDEN_RE.search(self.review_md([])))
        self.assertIsNone(_FORBIDDEN_RE.search("Nothing is ready for you."))


class QueueOrderTests(ReviewMdTestCase):
    def test_same_prs_and_order_as_the_queue_with_a_pin(self):
        self.track_ready("sess-1", 1, "qa/T01")
        self.track_ready("sess-1", 2, "qa/T02")
        self.track_ready("sess-1", 3, "qa/T03")
        self.track("sess-1", 4, "qa/T04", "draft")
        self.sync_gh("sess-1")
        self.run_cli(["merge-queue", "pin", "acme/app#3", "--before", "acme/app#1"], "sess-1", self.repo_dir)
        code, queue_out, err = self.run_cli(["merge-queue"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        queue_refs = _QUEUE_REF_RE.findall(queue_out)
        self.assertLess(queue_refs.index("acme/app#3"), queue_refs.index("acme/app#1"))
        expected = [ref for ref in queue_refs if ref != "acme/app#4"]
        self.assertEqual(self.refs(self.review_md([])), expected)
