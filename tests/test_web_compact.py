import json
import sqlite3

from tests.test_web_write import WebWriteTestCase


class WebCompactTests(WebWriteTestCase):
    def test_compact_runs_and_records_the_event(self):
        response, payload = self._post_json("/api/compact", self._good_headers(), {})
        self.assertEqual(response.status, 200, payload)
        self.assertIn("backup", json.loads(payload)["message"])
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        count = conn.execute("SELECT COUNT(*) FROM events WHERE kind = 'db.compacted'").fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_missing_token_is_403(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._post_json("/api/compact", headers, {})
        self.assertEqual(response.status, 403)

    def test_script_posts_to_the_endpoint(self):
        response, script = self._get("/app.js", self._host())
        self.assertIn(b'"/api/compact"', script)
