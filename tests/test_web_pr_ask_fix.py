import json

from tests.mq_fixtures import OPEN_VIEW
from tests.test_web_write import WebWriteTestCase

_ASK_FIX = "/api/prs/acme/app/1/ask-fix"
_FAILING_VIEW = dict(OPEN_VIEW, statusCheckRollup=[{"conclusion": "FAILURE"}], headRefOid="abc123")


class WebPrAskFixTests(WebWriteTestCase):
    def setUp(self):
        super().setUp()
        self.write_gh_fixture("view_acme-app_1", _FAILING_VIEW)
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "pr 1", "--waits", "review"],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def _board_pr(self):
        response, body = self._get("/api/board", self._host())
        board = json.loads(body)
        return board["parties"][0]["quests"][0]["tasks"][0]["prs"][0]

    def test_ask_fix_sets_the_head_flag(self):
        pr = self._board_pr()
        self.assertEqual((pr["party"], pr["fix_reasons"], pr["fix_requested_at_head"]), ("alpha", ["checks failing (1)"], False))
        response, payload = self._post_json(_ASK_FIX, self._good_headers(), {})
        self.assertEqual(response.status, 200, payload)
        self.assertTrue(self._board_pr()["fix_requested_at_head"])

    def test_new_head_clears_the_flag(self):
        self._post_json(_ASK_FIX, self._good_headers(), {})
        self.write_gh_fixture("view_acme-app_1", dict(_FAILING_VIEW, headRefOid="def456"))
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertFalse(self._board_pr()["fix_requested_at_head"])

    def test_refusal_is_422(self):
        self.run_cli(["pr", "set", "acme/app#1", "--blocked-external", "legal"], "sess-1", self.repo_dir)
        response, payload = self._post_json(_ASK_FIX, self._good_headers(), {})
        self.assertEqual(response.status, 422)
        self.assertIn("unblock it first", self._error(payload))

    def test_missing_token_and_wrong_origin_are_403(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._post_json(_ASK_FIX, headers, {})
        self.assertEqual(response.status, 403)
        headers = self._good_headers()
        headers["Origin"] = "http://evil.example"
        response, payload = self._post_json(_ASK_FIX, headers, {})
        self.assertEqual(response.status, 403)
