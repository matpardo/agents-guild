import json

from tests.test_web_write import WebWriteTestCase


class WebTaskDiscardTests(WebWriteTestCase):
    def _act(self, action, tid, data, headers=None):
        url = "/api/quests/demo/tasks/{}/{}".format(tid, action)
        return self._post_json(url, headers or self._good_headers(), data)

    def _quest(self):
        board = json.loads(self._get("/api/board", self._host())[1])
        party_model = next(item for item in board["parties"] if item["name"] == "alpha")
        return next(quest for quest in party_model["quests"] if quest["slug"] == "demo")

    def test_discard_then_restore(self):
        response, payload = self._act("discard", "T01", {"reason": "made by mistake", "force": False})
        self.assertEqual(response.status, 200, payload)
        quest = self._quest()
        self.assertEqual(quest["tasks"], [])
        discarded = quest["discarded"][0]
        self.assertEqual((discarded["tid"], discarded["reason"], discarded["by"]), ("T01", "made by mistake", "human"))
        self.assertIsNotNone(discarded["at"])
        response, payload = self._act("restore", "T01", {})
        self.assertEqual(response.status, 200, payload)
        quest = self._quest()
        self.assertEqual([task["tid"] for task in quest["tasks"]], ["T01"])
        self.assertEqual(quest["discarded"], [])

    def test_guard_failure_is_422(self):
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        response, payload = self._act("discard", "T01", {"reason": "x", "force": False})
        self.assertEqual(response.status, 422)
        self.assertIn("is active", self._error(payload))

    def test_force_discards_an_active_task(self):
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        response, payload = self._act("discard", "T01", {"reason": "x", "force": True})
        self.assertEqual(response.status, 200, payload)

    def test_restoring_a_task_that_is_not_discarded_is_422(self):
        response, payload = self._act("restore", "T01", {})
        self.assertEqual(response.status, 422)

    def test_bad_payload_is_400(self):
        response, payload = self._act("discard", "T01", {"reason": 3, "force": False})
        self.assertEqual(response.status, 400)
        response, payload = self._act("discard", "T01", {"reason": "x"})
        self.assertEqual(response.status, 400)

    def test_missing_token_is_403(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._act("discard", "T01", {"reason": "x", "force": False}, headers)
        self.assertEqual(response.status, 403)


if __name__ == "__main__":
    import unittest

    unittest.main()
