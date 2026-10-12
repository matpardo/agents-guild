import json

from tests.test_web_write import WebWriteTestCase


class MemoryWebTestCase(WebWriteTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["memory", "add", "remember this"], "sess-1", self.repo_dir)

    def _memory_rm(self, party, seq):
        return self._post_json("/api/memory/{}/{}/rm".format(party, seq), self._good_headers(), {})

    def _memory_items(self):
        response, body = self._get("/api/board", self._host())
        return json.loads(body)["memory"]

    def _error(self, payload):
        return json.loads(payload)["error"]


class MemoryActionTests(MemoryWebTestCase):
    def test_rm_succeeds_and_removes_the_item(self):
        response, payload = self._memory_rm("alpha", 1)
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(payload), {"ok": True, "message": "memory item alpha/1 removed"})
        self.assertEqual(self._memory_items(), [])

    def test_unknown_item_is_422(self):
        response, payload = self._memory_rm("alpha", 99)
        self.assertEqual(response.status, 422)
        self.assertIn("unknown memory item", self._error(payload))

    def test_rm_from_the_web_is_allowed_on_any_party(self):
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        self.run_cli(["memory", "add", "beta note"], "sess-2", self.repo_dir)
        response, payload = self._memory_rm("beta", 1)
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(payload), {"ok": True, "message": "memory item beta/1 removed"})

    def test_non_numeric_seq_in_url_is_405(self):
        response, payload = self._post_json("/api/memory/alpha/abc/rm", self._good_headers(), {})
        self.assertEqual(response.status, 405)

    def test_missing_token_is_403_and_leaves_the_item(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._post_json("/api/memory/alpha/1/rm", headers, {})
        self.assertEqual(response.status, 403)
        self.assertEqual(len(self._memory_items()), 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
