import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

from guild import paths
from guild.errors import GuildError
from tests import node_harness
from tests.test_web_write import WebWriteTestCase

_APP_JS = Path(__file__).resolve().parent.parent / "guild" / "web" / "app.js"
_HARNESS_NAME = "web_realm_harness.js"
_PROJECT = {"name": "app", "parties": 2, "open_quests": 3, "open_prs": 4, "ready_prs": 1, "open_asks": 5, "main_red": False}
_GUILD = {"guild": "alpha", "generated_at": "2026-10-24T09:59:00+00:00", "received_at": "2026-10-24T10:00:00+00:00", "projects": [_PROJECT]}
_RED_GUILD = {"guild": "beta", "generated_at": "2026-10-24T09:59:00+00:00", "received_at": "2026-10-24T10:00:00+00:00", "projects": [dict(_PROJECT, name="api", main_red=True)]}
_FILE = {"id": "0123456789abcdef", "from": "alpha", "name": "req.md", "size": 12, "sent_at": "2026-10-24T09:00:00+00:00"}
_FILE_TWO = dict(_FILE, id="fedcba9876543210", name="other.md")
_MODEL = {"fetched_at": "2026-10-24T10:00:00+00:00", "realm": "hearth", "guilds": [_GUILD, _RED_GUILD], "dropped": 0, "inbox": []}
_FLAG_TEXT = "read it yourself before giving it to an agent"


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
        self._write_cache(json.dumps({"fetched_at": _MODEL["fetched_at"], "realm": "hearth", "guilds": [_GUILD, _RED_GUILD]}))
        self.assertEqual(self._realm(), _MODEL)

    def test_cache_without_realm_is_empty(self):
        self._write_config()
        self._write_cache(json.dumps({"fetched_at": _MODEL["fetched_at"], "guilds": []}))
        self.assertIsNone(self._realm()["realm"])

    def test_guild_name_comes_from_the_global_config(self):
        response, body = self._get("/api/board", self._host())
        self.assertIsNone(json.loads(body)["guild_name"])
        paths.global_config_path().parent.mkdir(parents=True, exist_ok=True)
        paths.global_config_path().write_text(json.dumps({"name": "forge"}))
        response, body = self._get("/api/board", self._host())
        self.assertEqual(json.loads(body)["guild_name"], "forge")

    def test_missing_cache_is_empty(self):
        self._write_config()
        self.assertEqual(self._realm(), {"fetched_at": None, "realm": None, "guilds": [], "dropped": 0, "inbox": []})

    def test_bad_cache_is_empty(self):
        self._write_config()
        self._write_cache("{not json")
        self.assertEqual(self._realm(), {"fetched_at": None, "realm": None, "guilds": [], "dropped": 0, "inbox": []})

    def _write_inbox_cache(self, payload):
        path = paths.realm_inbox_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))

    def test_inbox_comes_from_the_inbox_cache_and_drops_invalid_entries(self):
        self._write_config()
        self._write_inbox_cache({"fetched_at": _MODEL["fetched_at"], "files": [_FILE, dict(_FILE, id="bad"), "x"]})
        self.assertEqual(self._realm()["inbox"], [_FILE])

    def test_bad_inbox_cache_is_an_empty_inbox(self):
        self._write_config()
        self._write_cache(json.dumps({"fetched_at": _MODEL["fetched_at"], "realm": "hearth", "guilds": []}))
        paths.realm_inbox_cache_path().write_text("{nope")
        self.assertEqual(self._realm()["inbox"], [])


class RealmInboxRouteTests(WebWriteTestCase):
    _ID = _FILE["id"]

    def _call(self, path, headers=None):
        return self._post_json(path, headers or self._good_headers(), {})

    def test_refresh_returns_the_inbox(self):
        model = {"fetched_at": _MODEL["fetched_at"], "files": [_FILE]}
        with mock.patch("guild.webserver.realm_commands.inbox_model", return_value=model) as command:
            response, payload = self._call("/api/realm/inbox/refresh")
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(json.loads(payload), dict(model, ok=True))
        self.assertIsNone(command.call_args[0][1])

    def test_fetch_saves_into_the_default_dir(self):
        result = {"path": "/x/req.md", "from": "alpha", "flagged": True}
        with mock.patch("guild.webserver.realm_commands.fetch", return_value=result) as command:
            response, payload = self._call("/api/realm/inbox/{}/fetch".format(self._ID))
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(json.loads(payload), dict(result, ok=True))
        command.assert_called_once_with(self._ID, str(paths.realm_files_dir()), None)

    def test_drop_calls_the_command(self):
        with mock.patch("guild.webserver.realm_commands.drop", return_value="dropped it") as command:
            response, payload = self._call("/api/realm/inbox/{}/drop".format(self._ID))
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(json.loads(payload), {"message": "dropped it", "ok": True})
        command.assert_called_once_with(self._ID, None)

    def test_guild_error_is_422_with_the_message(self):
        error = GuildError("realm hub refused (404): not found", 1)
        for action, target in (("fetch", "fetch"), ("drop", "drop")):
            with mock.patch("guild.webserver.realm_commands." + target, side_effect=error):
                response, payload = self._call("/api/realm/inbox/{}/{}".format(self._ID, action))
            self.assertEqual(response.status, 422)
            self.assertEqual(self._error(payload), "realm hub refused (404): not found")
        with mock.patch("guild.webserver.realm_commands.inbox_model", side_effect=error):
            response, payload = self._call("/api/realm/inbox/refresh")
        self.assertEqual(response.status, 422)

    def test_bad_ids_are_404_and_the_command_is_not_called(self):
        with mock.patch("guild.webserver.realm_commands.fetch") as fetch, mock.patch(
            "guild.webserver.realm_commands.drop"
        ) as drop:
            for bad in ("zz", "0123456789ABCDEF", "0123456789abcde", "0123456789abcdef0", "..%2f.."):
                for action in ("fetch", "drop"):
                    response, payload = self._call("/api/realm/inbox/{}/{}".format(bad, action))
                    self.assertEqual(response.status, 404, bad)
        fetch.assert_not_called()
        drop.assert_not_called()

    def test_token_and_origin_are_enforced(self):
        missing_token = self._good_headers()
        del missing_token["X-Guild-Token"]
        foreign = dict(self._good_headers(), Origin="http://evil.example")
        with mock.patch("guild.webserver.realm_commands.fetch") as fetch, mock.patch(
            "guild.webserver.realm_commands.drop"
        ) as drop, mock.patch("guild.webserver.realm_commands.inbox_model") as refresh:
            for headers in (missing_token, foreign):
                for path in (
                    "/api/realm/inbox/refresh",
                    "/api/realm/inbox/{}/fetch".format(self._ID),
                    "/api/realm/inbox/{}/drop".format(self._ID),
                ):
                    self.assertEqual(self._call(path, headers)[0].status, 403, path)
        for command in (fetch, drop, refresh):
            command.assert_not_called()


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


class RealmDoctorRouteTests(WebWriteTestCase):
    _LINES = [(True, "ok      token accepted"), (True, "warn    this guild never pushed"), (False, "fail    realm hub unreachable: OSError")]

    def test_returns_the_lines_and_overall_result(self):
        with mock.patch("guild.webserver.realm_commands.doctor_lines", return_value=self._LINES) as command:
            response, payload = self._post_json("/api/realm/doctor", self._good_headers(), {})
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(
            json.loads(payload),
            {
                "ok": False,
                "lines": [
                    {"passed": True, "text": "ok      token accepted"},
                    {"passed": True, "text": "warn    this guild never pushed"},
                    {"passed": False, "text": "fail    realm hub unreachable: OSError"},
                ],
            },
        )
        command.assert_called_once()

    def test_all_passing_is_ok(self):
        with mock.patch("guild.webserver.realm_commands.doctor_lines", return_value=self._LINES[:2]):
            response, payload = self._post_json("/api/realm/doctor", self._good_headers(), {})
        self.assertTrue(json.loads(payload)["ok"])

    def test_without_a_realm_it_still_answers(self):
        response, payload = self._post_json("/api/realm/doctor", self._good_headers(), {})
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(json.loads(payload), {"ok": True, "lines": [{"passed": True, "text": "ok      no realm joined"}]})

    def test_guild_error_is_422_with_the_message(self):
        error = GuildError("boom", 1)
        with mock.patch("guild.webserver.realm_commands.doctor_lines", side_effect=error):
            response, payload = self._post_json("/api/realm/doctor", self._good_headers(), {})
        self.assertEqual(response.status, 422)
        self.assertEqual(self._error(payload), "boom")

    def test_token_and_origin_are_enforced(self):
        missing_token = self._good_headers()
        del missing_token["X-Guild-Token"]
        foreign = dict(self._good_headers(), Origin="http://evil.example")
        with mock.patch("guild.webserver.realm_commands.doctor_lines") as command:
            for headers in (missing_token, foreign):
                self.assertEqual(self._post_json("/api/realm/doctor", headers, {})[0].status, 403)
        command.assert_not_called()


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class RealmPanelBehaviorTests(unittest.TestCase):
    def _panel(self, realm, refresh, clicks=None, replies=None, guild_name=None):
        return node_harness.request(
            _HARNESS_NAME,
            {
                "src": str(_APP_JS), "realm": realm, "refresh": refresh, "clicks": clicks or [],
                "replies": replies or {}, "guild_name": guild_name,
            },
        )

    def test_guilds_show_counts_and_red_marker(self):
        out = self._panel(_MODEL, None)
        for expected in ("alpha", "beta", "app: parties 2, quests 3, PRs 4 (1 ready), asks 5", "api: parties", "main red"):
            self.assertIn(expected, out["text"])
        self.assertTrue(out["red"])

    def test_heading_shows_the_realm_name_when_known(self):
        self.assertIn("realm hearth", self._panel(_MODEL, None)["text"])
        self.assertNotIn("realm hearth", self._panel(dict(_MODEL, realm=None), None)["text"])

    def test_header_shows_the_guild_name_when_set(self):
        self.assertEqual(self._panel(_MODEL, None, guild_name="forge")["title"], "guild board · forge")
        self.assertEqual(self._panel(_MODEL, None)["title"], "guild board")

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

    def _with_inbox(self):
        return dict(_MODEL, inbox=[_FILE, _FILE_TWO])

    def test_inbox_rows_show_sender_name_size_age_and_buttons(self):
        out = self._panel(self._with_inbox(), None)
        for expected in ("Inbox", "alpha req.md 12 bytes", "other.md", "Refresh inbox"):
            self.assertIn(expected, out["text"])
        self.assertEqual(out["text"].count("Fetch"), 2)
        self.assertEqual(out["text"].count("Drop"), 2)

    def test_empty_inbox_message(self):
        self.assertIn("inbox empty", self._panel(_MODEL, None)["text"])

    def test_fetch_shows_the_path_without_a_flag(self):
        replies = {"/api/realm/inbox/{}/fetch".format(_FILE["id"]): {"ok": True, "body": {"path": "/d/req.md", "from": "alpha", "flagged": False, "ok": True}}}
        out = self._panel(self._with_inbox(), None, [{"label": "Fetch", "index": 0}], replies)
        self.assertIn("saved /d/req.md from alpha", out["text"])
        self.assertNotIn(_FLAG_TEXT, out["text"])

    def test_fetch_shows_the_flag_when_flagged(self):
        replies = {"/api/realm/inbox/{}/fetch".format(_FILE_TWO["id"]): {"ok": True, "body": {"path": "/d/other.md", "from": "alpha", "flagged": True, "ok": True}}}
        out = self._panel(self._with_inbox(), None, [{"label": "Fetch", "index": 1}], replies)
        self.assertIn("saved /d/other.md", out["text"])
        self.assertIn(_FLAG_TEXT, out["text"])

    def test_fetch_error_text_is_shown(self):
        replies = {"/api/realm/inbox/{}/fetch".format(_FILE["id"]): {"ok": False, "body": {"error": "realm hub refused (404): not found"}}}
        out = self._panel(self._with_inbox(), None, [{"label": "Fetch", "index": 0}], replies)
        self.assertIn("realm hub refused (404): not found", out["text"])

    def test_drop_confirms_posts_and_refreshes_the_inbox(self):
        drop_url = "/api/realm/inbox/{}/drop".format(_FILE["id"])
        replies = {
            drop_url: {"ok": True, "body": {"message": "dropped", "ok": True}},
            "/api/realm/inbox/refresh": {"ok": True, "body": {"fetched_at": _MODEL["fetched_at"], "files": [_FILE_TWO], "ok": True}},
        }
        out = self._panel(self._with_inbox(), None, [{"label": "Drop", "index": 0}], replies)
        self.assertEqual(out["posts"], [drop_url, "/api/realm/inbox/refresh"])
        self.assertNotIn("req.md", out["text"])
        self.assertIn("other.md", out["text"])

    def test_refresh_inbox_button_replaces_the_rows(self):
        replies = {"/api/realm/inbox/refresh": {"ok": True, "body": {"fetched_at": _MODEL["fetched_at"], "files": [_FILE_TWO], "ok": True}}}
        out = self._panel(self._with_inbox(), None, [{"label": "Refresh inbox", "index": 0}], replies)
        self.assertNotIn("req.md", out["text"])
        self.assertIn("other.md", out["text"])

    def test_realm_refresh_also_refreshes_the_inbox(self):
        fresh = dict(_MODEL, ok=True)
        replies = {"/api/realm/inbox/refresh": {"ok": True, "body": {"fetched_at": _MODEL["fetched_at"], "files": [_FILE_TWO], "ok": True}}}
        out = self._panel(self._with_inbox(), {"ok": True, "body": fresh}, None, replies)
        self.assertEqual(out["posts"], ["/api/realm/inbox/refresh"])
        self.assertIn("other.md", out["text"])
        self.assertNotIn("req.md", out["text"])

    def test_inbox_error_text_is_shown(self):
        replies = {"/api/realm/inbox/refresh": {"ok": False, "body": {"error": "realm hub request failed: URLError"}}}
        out = self._panel(self._with_inbox(), None, [{"label": "Refresh inbox", "index": 0}], replies)
        self.assertIn("realm hub request failed: URLError", out["text"])
        self.assertIn("req.md", out["text"])

    def test_check_renders_lines_with_failures_marked(self):
        lines = [
            {"passed": True, "text": "ok      token accepted"},
            {"passed": True, "text": "warn    this guild never pushed"},
            {"passed": False, "text": "fail    realm hub unreachable: OSError"},
        ]
        replies = {"/api/realm/doctor": {"ok": True, "body": {"ok": False, "lines": lines}}}
        out = self._panel(_MODEL, None, [{"label": "Check", "index": 0}], replies)
        for line in lines:
            self.assertIn(line["text"], out["text"])
        self.assertTrue(out["red"])

    def test_check_with_only_passing_lines_has_no_bad_marker(self):
        replies = {"/api/realm/doctor": {"ok": True, "body": {"ok": True, "lines": [{"passed": True, "text": "ok      token accepted"}]}}}
        out = self._panel(dict(_MODEL, guilds=[_GUILD]), None, [{"label": "Check", "index": 0}], replies)
        self.assertIn("ok      token accepted", out["text"])
        self.assertFalse(out["red"])

    def test_check_error_text_is_shown(self):
        replies = {"/api/realm/doctor": {"ok": False, "body": {"error": "boom"}}}
        out = self._panel(_MODEL, None, [{"label": "Check", "index": 0}], replies)
        self.assertIn("boom", out["text"])
