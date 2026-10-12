import json

from tests.test_web_write import WebWriteTestCase


class WebDispatchPauseTests(WebWriteTestCase):
    def _dispatcher(self):
        response, body = self._get("/api/board", self._host())
        return json.loads(body)["dispatcher"]

    def _pause(self, reason="incident"):
        return self._post_json("/api/dispatch/pause", self._good_headers(), {"reason": reason})

    def _resume(self):
        return self._post_json("/api/dispatch/resume", self._good_headers(), {})

    def test_pause_and_resume_work_for_the_human(self):
        response, payload = self._pause("deploy freeze")
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(self._dispatcher()["paused"]["reason"], "deploy freeze")
        response, payload = self._resume()
        self.assertEqual(response.status, 200, payload)
        self.assertIsNone(self._dispatcher()["paused"])

    def test_double_pause_is_422(self):
        self._pause()
        response, payload = self._pause()
        self.assertEqual(response.status, 422)

    def test_resume_when_not_paused_is_422(self):
        response, payload = self._resume()
        self.assertEqual(response.status, 422)

    def test_missing_reason_is_422(self):
        response, payload = self._post_json("/api/dispatch/pause", self._good_headers(), {})
        self.assertEqual(response.status, 422)
        self.assertIsNone(self._dispatcher()["paused"])

    def test_empty_reason_is_422(self):
        response, payload = self._pause("")
        self.assertEqual(response.status, 422)

    def test_overlong_reason_is_422(self):
        response, payload = self._pause("x" * 301)
        self.assertEqual(response.status, 422)

    def test_missing_token_and_wrong_origin_are_403(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._post_json("/api/dispatch/pause", headers, {"reason": "x"})
        self.assertEqual(response.status, 403)
        headers = self._good_headers()
        headers["Origin"] = "http://evil.example"
        response, payload = self._post_json("/api/dispatch/pause", headers, {"reason": "x"})
        self.assertEqual(response.status, 403)
        self.assertIsNone(self._dispatcher()["paused"])

    def test_web_resume_counts_as_human(self):
        self.run_cli(["dispatch", "pause", "--reason", "x"], "sess-1", self.repo_dir)
        response, payload = self._resume()
        self.assertEqual(response.status, 200, payload)
        self.assertIsNone(self._dispatcher()["paused"])


if __name__ == "__main__":
    import unittest

    unittest.main()
