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

    def test_ask_fix_opens_the_request(self):
        pr = self._board_pr()
        self.assertEqual((pr["party"], pr["fix_reasons"], pr["fix_request"]), ("alpha", ["checks failing (1)"], None))
        response, payload = self._post_json(_ASK_FIX, self._good_headers(), {})
        self.assertEqual(response.status, 200, payload)
        request = self._board_pr()["fix_request"]
        self.assertEqual((request["party"], request["age_hours"], request["stale"]), ("alpha", 0, False))

    def test_new_head_keeps_the_request(self):
        self._post_json(_ASK_FIX, self._good_headers(), {})
        self.write_gh_fixture("view_acme-app_1", dict(_FAILING_VIEW, headRefOid="def456"))
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertIsNotNone(self._board_pr()["fix_request"])

    def test_cleared_blockers_close_the_request(self):
        self._post_json(_ASK_FIX, self._good_headers(), {})
        self.write_gh_fixture("view_acme-app_1", dict(OPEN_VIEW, headRefOid="def456"))
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertIsNone(self._board_pr()["fix_request"])

    def test_second_request_is_422(self):
        self._post_json(_ASK_FIX, self._good_headers(), {})
        response, payload = self._post_json(_ASK_FIX, self._good_headers(), {})
        self.assertEqual(response.status, 422)
        self.assertIn("fix already requested", self._error(payload))

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
