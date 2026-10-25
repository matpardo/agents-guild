import json

from tests.test_web_write import WebWriteTestCase


class WebTaskMoveTests(WebWriteTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-2", self.repo_dir)
        self.run_cli(["quest", "add", "other", "--title", "Other", "--no-epic"], "sess-2", self.repo_dir)

    def _move(self, tid, data, headers=None):
        return self._post_json("/api/quests/demo/tasks/{}/move".format(tid), headers or self._good_headers(), data)

    def _quest(self, party, slug):
        board = json.loads(self._get("/api/board", self._host())[1])
        party_model = next(item for item in board["parties"] if item["name"] == party)
        return next(quest for quest in party_model["quests"] if quest["slug"] == slug)

    def test_move_succeeds(self):
        response, payload = self._move("T01", {"to": "other"})
        self.assertEqual(response.status, 200, payload)
        self.assertEqual([task["tid"] for task in self._quest("beta", "other")["tasks"]], ["T01"])
        self.assertEqual(self._quest("alpha", "demo")["tasks"], [])

    def test_guard_failure_is_422(self):
        response, payload = self._move("T01", {"to": "ghost"})
        self.assertEqual(response.status, 422)
        self.assertIn("unknown quest", self._error(payload))

    def test_unknown_task_is_422(self):
        response, payload = self._move("T99", {"to": "other"})
        self.assertEqual(response.status, 422)

    def test_non_string_target_is_400(self):
        response, payload = self._move("T01", {"to": 3})
        self.assertEqual(response.status, 400)

    def test_missing_token_is_403(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._move("T01", {"to": "other"}, headers)
        self.assertEqual(response.status, 403)

    def test_board_lists_move_targets(self):
        self.assertEqual(self._quest("alpha", "demo")["move_targets"], ["other"])


if __name__ == "__main__":
    import unittest

    unittest.main()
