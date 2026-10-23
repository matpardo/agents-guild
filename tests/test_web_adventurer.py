import json

from tests.test_web_write import WebWriteTestCase


class WebAdventurerDismissTests(WebWriteTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["adventurer", "start", "fix typo"], "adv-1", self.repo_dir)

    def _adventurers(self):
        response, body = self._get("/api/board", self._host())
        return json.loads(body)["adventurers"]

    def _dismiss(self, adventurer_id):
        return self._post_json("/api/adventurers/{}/dismiss".format(adventurer_id), self._good_headers(), {})

    def test_done_adventurer_is_dismissed_through_the_same_command(self):
        self.run_cli(["adventurer", "done", "--pending", "none"], "adv-1", self.repo_dir)
        self.assertEqual(self._adventurers()[0]["state"], "done")
        response, payload = self._dismiss(1)
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(self._adventurers(), [])

    def test_active_or_unknown_adventurer_is_422(self):
        self.assertEqual(self._dismiss(1)[0].status, 422)
        self.assertEqual(self._dismiss(9)[0].status, 422)

    def test_bad_id_is_404(self):
        self.assertEqual(self._dismiss("abc")[0].status, 404)

    def test_missing_token_is_403(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._post_json("/api/adventurers/1/dismiss", headers, {})
        self.assertEqual(response.status, 403)
