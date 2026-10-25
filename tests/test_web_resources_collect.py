import json
from unittest import mock

from tests.test_web_write import WebWriteTestCase


class WebResourcesCollectTests(WebWriteTestCase):
    def test_collect_runs_and_returns_the_summary(self):
        with mock.patch("guild.webserver.resources_commands.run_collect", return_value="sampled 1 project") as run:
            response, payload = self._post_json("/api/resources/collect", self._good_headers(), {})
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(json.loads(payload)["message"], "sampled 1 project")
        run.assert_called_once()

    def test_missing_token_is_403(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._post_json("/api/resources/collect", headers, {})
        self.assertEqual(response.status, 403)

    def test_script_posts_to_the_endpoint(self):
        response, script = self._get("/app.js", self._host())
        self.assertIn(b'"/api/resources/collect"', script)
