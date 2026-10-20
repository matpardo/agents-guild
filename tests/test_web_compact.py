import json
import shutil
import sqlite3
import subprocess
import unittest
from pathlib import Path
from unittest import mock

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

    def test_database_error_is_a_json_500(self):
        error = sqlite3.OperationalError("database is locked")
        with mock.patch("guild.webserver.compact_commands.run", side_effect=error):
            response, payload = self._post_json("/api/compact", self._good_headers(), {})
        self.assertEqual(response.status, 500)
        self.assertEqual(json.loads(payload)["error"], "database is locked")

    def test_missing_token_is_403(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._post_json("/api/compact", headers, {})
        self.assertEqual(response.status, 403)

    def test_script_posts_to_the_endpoint(self):
        response, script = self._get("/app.js", self._host())
        self.assertIn(b'"/api/compact"', script)


_COMPACT_HARNESS = Path(__file__).resolve().parent / "web_compact_harness.js"
_APP_JS = Path(__file__).resolve().parent.parent / "guild" / "web" / "app.js"


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebCompactButtonBehaviorTests(unittest.TestCase):
    def _after_click(self, scenario):
        result = subprocess.run(
            ["node", str(_COMPACT_HARNESS), str(_APP_JS), scenario],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return json.loads(result.stdout)

    def test_failed_post_with_failed_refresh_leaves_compacting_and_shows_the_error(self):
        after = self._after_click("dropped")
        self.assertFalse(after["disabled"])
        self.assertNotIn("compacting...", after["text"])
        self.assertIn("request failed", after["text"])

    def test_success_with_failed_refresh_shows_the_result_lines(self):
        after = self._after_click("ok")
        self.assertFalse(after["disabled"])
        self.assertNotIn("compacting...", after["text"])
        self.assertIn("backup done", after["text"])
        self.assertIn("vacuum done", after["text"])
