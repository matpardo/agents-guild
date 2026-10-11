import json

from tests.test_web_write import WebWriteTestCase


class WebRaidPauseTests(WebWriteTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["raid", "join", "ci", "--ttl", "8h", "--lead"], "sess-1", self.repo_dir)

    def _paused(self):
        response, body = self._get("/api/board", self._host())
        return [raid["paused"] for raid in json.loads(body)["raids"] if raid["name"] == "ci"][0]

    def test_pause_and_resume_work_for_the_human(self):
        response, payload = self._post_json("/api/raids/ci/pause", self._good_headers(), {})
        self.assertEqual(response.status, 200, payload)
        self.assertTrue(self._paused())
        response, payload = self._post_json("/api/raids/ci/resume", self._good_headers(), {})
        self.assertEqual(response.status, 200, payload)
        self.assertFalse(self._paused())

    def test_double_pause_unknown_raid_and_bad_resume_are_422(self):
        self._post_json("/api/raids/ci/pause", self._good_headers(), {})
        response, payload = self._post_json("/api/raids/ci/pause", self._good_headers(), {})
        self.assertEqual(response.status, 422)
        response, payload = self._post_json("/api/raids/nope/pause", self._good_headers(), {})
        self.assertEqual(response.status, 422)
        self._post_json("/api/raids/ci/resume", self._good_headers(), {})
        response, payload = self._post_json("/api/raids/ci/resume", self._good_headers(), {})
        self.assertEqual(response.status, 422)

    def test_resume_announces_to_the_raid(self):
        self._post_json("/api/raids/ci/pause", self._good_headers(), {})
        self._post_json("/api/raids/ci/resume", self._good_headers(), {})
        response, body = self._get("/api/board", self._host())
        self.assertEqual([n["text"] for n in json.loads(body)["notices"]], ["raid ci resumed"])

    def test_missing_token_and_wrong_origin_are_403(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._post_json("/api/raids/ci/pause", headers, {})
        self.assertEqual(response.status, 403)
        headers = self._good_headers()
        headers["Origin"] = "http://evil.example"
        response, payload = self._post_json("/api/raids/ci/pause", headers, {})
        self.assertEqual(response.status, 403)
        self.assertFalse(self._paused())
