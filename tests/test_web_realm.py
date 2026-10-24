import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

from guild import paths
from guild.commands import board as board_commands
from guild.errors import GuildError
from tests import node_harness
from tests.test_web_write import WebWriteTestCase

_APP_JS = Path(__file__).resolve().parent.parent / "guild" / "web" / "app.js"
_HARNESS_NAME = "web_realm_harness.js"
_PROJECT = {"name": "app", "parties": 2, "open_quests": 3, "open_prs": 4, "ready_prs": 1, "open_asks": 5, "main_red": False}
_GUILD = {"guild": "alpha", "generated_at": "2026-10-24T09:59:00+00:00", "received_at": "2026-10-24T10:00:00+00:00", "projects": [_PROJECT]}
_RED_GUILD = {"guild": "beta", "generated_at": "2026-10-24T09:59:00+00:00", "received_at": "2026-10-24T10:00:00+00:00", "projects": [dict(_PROJECT, name="api", main_red=True)]}
_MODEL = {"fetched_at": "2026-10-24T10:00:00+00:00", "guilds": [_GUILD, _RED_GUILD], "dropped": 0}


class _RealmFiles:
    def _write_config(self):
        path = paths.realm_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    def _write_cache(self, text):
        path = paths.realm_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class RealmBoardModelTests(_RealmFiles, WebWriteTestCase):
    def _realm(self):
        response, body = self._get("/api/board", self._host())
        return json.loads(body)["realm"]

    def test_no_config_is_none(self):
        self.assertIsNone(self._realm())

    def test_config_and_cache_give_the_cached_model(self):
        self._write_config()
        self._write_cache(json.dumps({"fetched_at": _MODEL["fetched_at"], "guilds": [_GUILD, _RED_GUILD]}))
        self.assertEqual(self._realm(), _MODEL)

    def test_missing_cache_is_empty(self):
        self._write_config()
        self.assertEqual(self._realm(), {"fetched_at": None, "guilds": [], "dropped": 0})

    def test_bad_cache_is_empty(self):
        self._write_config()
        self._write_cache("{not json")
        self.assertEqual(self._realm(), {"fetched_at": None, "guilds": [], "dropped": 0})


class RealmRefreshRouteTests(WebWriteTestCase):
    def test_refresh_returns_the_model(self):
        with mock.patch("guild.webserver.realm_commands.realm_status_model", return_value=dict(_MODEL, dropped=1)):
            response, payload = self._post_json("/api/realm/refresh", self._good_headers(), {})
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(json.loads(payload), dict(_MODEL, dropped=1, ok=True))

    def test_guild_error_is_422_with_the_message(self):
        error = GuildError("realm hub request failed: URLError", 1)
        with mock.patch("guild.webserver.realm_commands.realm_status_model", side_effect=error):
            response, payload = self._post_json("/api/realm/refresh", self._good_headers(), {})
        self.assertEqual(response.status, 422)
        self.assertEqual(self._error(payload), "realm hub request failed: URLError")

    def test_missing_token_is_403_and_command_not_called(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        with mock.patch("guild.webserver.realm_commands.realm_status_model") as command:
            response, payload = self._post_json("/api/realm/refresh", headers, {})
        self.assertEqual(response.status, 403)
        command.assert_not_called()

    def test_foreign_origin_is_403(self):
        headers = dict(self._good_headers(), Origin="http://evil.example")
        response, payload = self._post_json("/api/realm/refresh", headers, {})
        self.assertEqual(response.status, 403)

    def test_without_config_the_command_error_is_422(self):
        response, payload = self._post_json("/api/realm/refresh", self._good_headers(), {})
        self.assertEqual(response.status, 422)
        self.assertIn("realm", self._error(payload))


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class RealmPanelBehaviorTests(unittest.TestCase):
    def _panel(self, realm, refresh):
        return node_harness.request(_HARNESS_NAME, {"src": str(_APP_JS), "realm": realm, "refresh": refresh})

    def test_guilds_show_counts_and_red_marker(self):
        out = self._panel(_MODEL, None)
        for expected in ("alpha", "beta", "app: parties 2, quests 3, PRs 4 (1 ready), asks 5", "api: parties", "main red"):
            self.assertIn(expected, out["text"])
        self.assertTrue(out["red"])

    def test_green_main_has_no_marker(self):
        out = self._panel(dict(_MODEL, guilds=[_GUILD]), None)
        self.assertFalse(out["red"])
        self.assertNotIn("main red", out["text"])

    def test_empty_guilds_message(self):
        out = self._panel({"fetched_at": None, "guilds": [], "dropped": 0}, None)
        self.assertIn("no guilds reported yet", out["text"])
        self.assertIn("never fetched", out["text"])

    def test_null_realm_renders_nothing(self):
        out = self._panel(None, None)
        self.assertEqual(out["text"], "")
        self.assertFalse(out["hasButton"])

    def test_refresh_error_text_is_shown(self):
        out = self._panel(_MODEL, {"ok": False, "body": {"error": "realm hub request failed: URLError"}})
        self.assertIn("realm hub request failed: URLError", out["text"])
        self.assertIn("alpha", out["text"])

    def test_refresh_success_replaces_the_guilds(self):
        fresh = dict(_MODEL, guilds=[dict(_GUILD, guild="gamma")], ok=True)
        out = self._panel(_MODEL, {"ok": True, "body": fresh})
        self.assertIn("gamma", out["text"])
        self.assertNotIn("beta", out["text"])
