import json
import sqlite3
import unittest

from guild import human_ready
from tests.mq_fixtures import OPEN_VIEW, MergeQueueTestCase

_HEAD = "2026-10-20T10:00:00Z"


def _comment(login, created_at):
    return {"author": {"login": login}, "createdAt": created_at}


def _review(login, submitted_at):
    return {"author": {"login": login}, "submittedAt": submitted_at}


class CommentsAfterHeadTests(unittest.TestCase):
    def test_counts_only_strictly_later_entries(self):
        comments = [_comment("bot", "2026-10-20T09:59:59Z"), _comment("bot", _HEAD), _comment("bot", "2026-10-20T10:00:01Z")]
        self.assertEqual(human_ready.comments_after_head(_HEAD, "me", comments, []), 1)

    def test_excludes_the_pr_author(self):
        comments = [_comment("me", "2026-10-20T11:00:00Z"), _comment("bot", "2026-10-20T11:00:00Z")]
        self.assertEqual(human_ready.comments_after_head(_HEAD, "me", comments, []), 1)

    def test_counts_reviews_by_submitted_at(self):
        reviews = [_review("bot", "2026-10-20T11:00:00Z"), _review("me", "2026-10-20T11:00:00Z")]
        self.assertEqual(human_ready.comments_after_head(_HEAD, "me", [], reviews), 1)

    def test_without_commits_is_unknown(self):
        self.assertIsNone(human_ready.comments_after_head(None, "me", [_comment("bot", _HEAD)], []))

    def test_deleted_author_counts_as_another_author(self):
        comments = [{"author": None, "createdAt": "2026-10-20T11:00:00Z"}]
        self.assertEqual(human_ready.comments_after_head(_HEAD, "me", comments, []), 1)


class CiLabelFlagTests(unittest.TestCase):
    def test_none_without_config(self):
        self.assertIsNone(human_ready.ci_label_flag({"name": "acme"}, [{"name": "run-ci"}]))

    def test_none_without_project(self):
        self.assertIsNone(human_ready.ci_label_flag(None, []))

    def test_flag_follows_label_presence(self):
        project = {"human_ready": {"ci_label": "run-ci"}}
        self.assertEqual(human_ready.ci_label_flag(project, [{"name": "run-ci"}]), 1)
        self.assertEqual(human_ready.ci_label_flag(project, [{"name": "other"}]), 0)


class SyncFreshnessFactsTests(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        self.start_party("alpha", "sess-1")
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.track("sess-1", 1, "demo/T01", "ready")

    def _view(self, **extra):
        view = dict(
            OPEN_VIEW,
            author={"login": "me"},
            labels=[{"name": "run-ci"}],
            commits=[{"committedDate": _HEAD}],
            comments=[_comment("bot", "2026-10-20T11:00:00Z"), _comment("me", "2026-10-20T11:00:00Z")],
            reviews=[_review("bot", "2026-10-20T09:00:00Z")],
        )
        view.update(extra)
        self.write_gh_fixture("view_acme-app_1", view)

    def _row(self):
        return self.query("SELECT comments_after_head, ci_label FROM prs WHERE number = 1")[0]

    def _set_ci_label(self):
        self._set_project_config({"human_ready": {"ci_label": "run-ci"}})

    def test_stores_comment_count_and_no_label_flag_without_config(self):
        self._view()
        self.assertEqual(self.sync_gh("sess-1")[0], 0)
        row = self._row()
        self.assertEqual(row["comments_after_head"], 1)
        self.assertIsNone(row["ci_label"])

    def test_stores_label_flag_when_configured(self):
        self._set_ci_label()
        self._view()
        self.sync_gh("sess-1")
        self.assertEqual(self._row()["ci_label"], 1)
        self._view(labels=[])
        self.sync_gh("sess-1")
        self.assertEqual(self._row()["ci_label"], 0)

    def test_no_commits_stores_null(self):
        self._view(commits=[])
        self.sync_gh("sess-1")
        self.assertIsNone(self._row()["comments_after_head"])

    def test_rebuild_reproduces_the_columns(self):
        self._set_ci_label()
        self._view()
        self.sync_gh("sess-1")
        before = dict(self._row())
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(dict(self._row()), before)
