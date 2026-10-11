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
            "sess-1", self.repo_dir,
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
