import json
import sqlite3

from tests.mq_fixtures import OPEN_VIEW
from tests.test_web_write import WebWriteTestCase

_BLOCK = "/api/prs/acme/app/1/block"
_UNBLOCK = "/api/prs/acme/app/1/unblock"


class WebPrBlockTests(WebWriteTestCase):
    def setUp(self):
        super().setUp()
        self.write_gh_fixture("view_acme-app_1", OPEN_VIEW)
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "pr 1", "--waits", "review"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)

    def _blocked(self):
        response, body = self._get("/api/board", self._host())
        return self._board_pr(json.loads(body))["blocked_external"]

    def _board_pr(self, board):
        for party in board["parties"]:
            for quest in party["quests"]:
                for task in quest["tasks"]:
                    for pr in task["prs"]:
                        return pr
        raise AssertionError("no pr on the board")

    def _query(self, sql):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def test_block_sets_the_flag_and_unblock_clears_it(self):
        response, payload = self._post_json(_BLOCK, self._good_headers(), {"reason": " team meeting "})
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(self._blocked(), "team meeting")
        response, payload = self._post_json(_UNBLOCK, self._good_headers(), {})
        self.assertEqual(response.status, 200, payload)
        self.assertIsNone(self._blocked())

    def test_block_keeps_the_other_fields(self):
        self.run_cli(["pr", "set", "acme/app#1", "--fixes-main"], "sess-1", self.repo_dir)
        self._post_json(_BLOCK, self._good_headers(), {"reason": "decision"})
        code, out, err = self.run_cli(["merge-queue"], "sess-1", self.repo_dir)
        self.assertIn("fixes-main", out)
        self.assertIn("blocked-external", out)

    def _unseen(self):
        return self._query("SELECT review_comment_count - COALESCE(last_notified_comment_count, 0) AS n FROM prs")[0][
            "n"
        ]

    def test_ack_marks_the_review_comments_as_read(self):
        view = dict(OPEN_VIEW, comments=[{"author": {"login": "bot"}, "createdAt": "2026-10-20T11:00:00Z"}])
        self.write_gh_fixture("view_acme-app_1", view)
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertGreater(self._unseen(), 0)
        response, payload = self._post_json("/api/prs/acme/app/1/ack", self._good_headers(), {})
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(self._unseen(), 0)

    def test_ack_of_an_unknown_pr_is_422(self):
        response, payload = self._post_json("/api/prs/acme/app/9/ack", self._good_headers(), {})
        self.assertEqual(response.status, 422)

    def test_empty_reason_is_422(self):
        response, payload = self._post_json(_BLOCK, self._good_headers(), {"reason": "   "})
        self.assertEqual(response.status, 422)
        self.assertIsNone(self._blocked())

    def test_non_string_reason_is_400(self):
        response, payload = self._post_json(_BLOCK, self._good_headers(), {"reason": 3})
        self.assertEqual(response.status, 400)

    def test_unknown_pr_is_422(self):
        response, payload = self._post_json("/api/prs/acme/app/9/block", self._good_headers(), {"reason": "x"})
        self.assertEqual(response.status, 422)
        self.assertIn("not tracked", self._error(payload))
        response, payload = self._post_json("/api/prs/acme/app/9/unblock", self._good_headers(), {})
        self.assertEqual(response.status, 422)

    def test_missing_token_and_wrong_origin_are_403(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._post_json(_BLOCK, headers, {"reason": "x"})
        self.assertEqual(response.status, 403)
        headers = self._good_headers()
        headers["Origin"] = "http://evil.example"
        response, payload = self._post_json(_UNBLOCK, headers, {})
        self.assertEqual(response.status, 403)
        self.assertIsNone(self._blocked())

    def test_event_is_recorded_without_a_party(self):
        self._post_json(_BLOCK, self._good_headers(), {"reason": "decision"})
        rows = self._query("SELECT party, project, payload FROM events WHERE kind = 'pr.set' ORDER BY seq DESC LIMIT 1")
        self.assertIsNone(rows[0]["party"])
        self.assertEqual(rows[0]["project"], "acme")
        self.assertEqual(json.loads(rows[0]["payload"])["blocked_external"], "decision")

    def _link(self):
        rows = self._query("SELECT task_tid, card FROM prs")
        return (rows[0]["task_tid"], rows[0]["card"]) if rows else None

    def test_relink_sets_the_card(self):
        response, payload = self._post_json("/api/prs/acme/app/1/relink", self._good_headers(), {"card": "DEMO-7"})
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(self._link(), ("T01", "DEMO-7"))

    def test_relink_moves_the_task(self):
        self.run_cli(["task", "add", "demo/T02", "--title", "Second"], "sess-1", self.repo_dir)
        response, payload = self._post_json("/api/prs/acme/app/1/relink", self._good_headers(), {"task": "demo/T02"})
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(self._link(), ("T02", None))

    def test_relink_without_target_is_422(self):
        response, payload = self._post_json("/api/prs/acme/app/1/relink", self._good_headers(), {})
        self.assertEqual(response.status, 422)

    def test_relink_unknown_task_is_422(self):
        response, payload = self._post_json("/api/prs/acme/app/1/relink", self._good_headers(), {"task": "demo/T99"})
        self.assertEqual(response.status, 422)

    def test_relink_non_string_is_400(self):
        response, payload = self._post_json("/api/prs/acme/app/1/relink", self._good_headers(), {"card": 3})
        self.assertEqual(response.status, 400)

    def test_untrack_removes_the_pr(self):
        response, payload = self._post_json("/api/prs/acme/app/1/untrack", self._good_headers(), {})
        self.assertEqual(response.status, 200, payload)
        self.assertIsNone(self._link())

    def test_untrack_unknown_pr_is_422(self):
        response, payload = self._post_json("/api/prs/acme/app/9/untrack", self._good_headers(), {})
        self.assertEqual(response.status, 422)
