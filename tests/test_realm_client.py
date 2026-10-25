import http.client
import json
import os
import shutil
import ssl
import stat
import unittest
from unittest import mock

from guild import db, paths, timeutil
from guild.commands import realm as realm_commands
from guild.context import RunContext
from guild.errors import GuildError
from guild.realm import checks as realm_checks
from guild.realm import client, clientconfig, hubconfig, pin, snapshot, status
from tests import realm_hub_fixture
from tests.testutil import GuildTestCase


def _insert(conn, sql, parameters):
    conn.execute(sql, parameters)


@unittest.skipUnless(shutil.which("openssl"), "openssl not on PATH")
class RealmClientTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("CLAUDECODE", None)
        self.server, self.cert, self.tokens = realm_hub_fixture.start_hub(self)
        self.url = "https://127.0.0.1:{}".format(self.server.server_address[1])
        self.fingerprint = pin.cert_fingerprint(self.cert)

    def _name_guild(self, name):
        paths.global_config_path().parent.mkdir(parents=True, exist_ok=True)
        paths.global_config_path().write_text(json.dumps({"name": name}))

    def _join(self, member, extra):
        self._name_guild(member)
        argv = ["realm", "join", self.url, "--fingerprint", self.fingerprint] + extra
        with mock.patch("getpass.getpass", return_value=self.tokens[member]):
            return self.run_cli(argv, None, self.root)

    def _seed(self):
        self.register_project("acme", ["acme/app", "acme/lib"])
        self.register_project("idle", ["acme/idle"])
        conn = db.connect(paths.db_path())
        try:
            _insert(
                conn, "INSERT INTO parties (name, project, generation, state) VALUES ('p1', 'acme', 1, 'active')", ()
            )
            _insert(
                conn, "INSERT INTO parties (name, project, generation, state) VALUES ('p2', 'acme', 1, 'closed')", ()
            )
            _insert(
                conn,
                "INSERT INTO quests (slug, project, party, epic, title, state) VALUES ('q1', 'acme', 'p1', NULL, 't', 'active')",
                (),
            )
            _insert(
                conn,
                "INSERT INTO quests (slug, project, party, epic, title, state) VALUES ('q2', 'acme', 'p1', NULL, 't', 'done')",
                (),
            )
            for repo, number, lifecycle in (
                ("acme/app", 1, "ready"),
                ("acme/lib", 2, "draft"),
                ("acme/app", 3, "merged"),
                ("acme/idle", 4, "closed"),
            ):
                _insert(
                    conn,
                    "INSERT INTO prs (repo, number, party, what, lifecycle, seeded) VALUES (?, ?, 'p1', 'w', ?, 0)",
                    (repo, number, lifecycle),
                )
            _insert(
                conn,
                "INSERT INTO asks (id, party, question, context, refs, options, state, created_at) VALUES (1, 'p1', 'q', 'c', '[]', '[]', 'open', '2026-10-24T10:00:00+00:00')",
                (),
            )
            _insert(
                conn,
                "INSERT INTO asks (id, party, question, context, refs, options, state, created_at) VALUES (2, 'p1', 'q', 'c', '[]', '[]', 'answered', '2026-10-24T10:00:00+00:00')",
                (),
            )
            _insert(
                conn,
                "INSERT INTO main_status (repo, source, red, reason, updated_at) VALUES ('acme/lib', 'manual', 1, 'r', '2026-10-24T10:00:00+00:00')",
                (),
            )
            _insert(
                conn,
                "INSERT INTO main_status (repo, source, red, reason, updated_at, external) VALUES ('acme/idle', 'gh', 1, 'billing', '2026-10-24T10:00:00+00:00', 'billing')",
                (),
            )
        finally:
            conn.close()

    def test_join_writes_private_config_and_refuses_overwrite(self):
        code, out, err = self._join("alpha", [])
        self.assertEqual(code, 0, err)
        path = paths.realm_config_path()
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        saved = json.loads(path.read_text())
        self.assertEqual(saved["guild"], "alpha")
        self.assertEqual(saved["realm"], realm_hub_fixture.REALM)
        self.assertIn("joined realm test-realm", out)
        self.assertEqual(saved["token"], self.tokens["alpha"])
        self.assertEqual(saved["fingerprint"], self.fingerprint)
        self.assertNotEqual(self._join("alpha", [])[0], 0)
        self.assertEqual(self._join("alpha", ["--force"])[0], 0)

    def test_join_without_a_guild_name_says_where_to_set_it(self):
        with mock.patch("getpass.getpass", return_value=self.tokens["alpha"]):
            code, out, err = self.run_cli(
                ["realm", "join", self.url, "--fingerprint", self.fingerprint], None, self.root
            )
        self.assertNotEqual(code, 0)
        self.assertIn('set "name" in {}'.format(paths.global_config_path()), err)
        self.assertIn("suggested: ", err)
        self.assertFalse(paths.realm_config_path().exists())

    def test_join_with_a_token_of_another_member_writes_nothing(self):
        self._name_guild("alpha")
        argv = ["realm", "join", self.url, "--fingerprint", self.fingerprint]
        with mock.patch("getpass.getpass", return_value=self.tokens["beta"]):
            code, out, err = self.run_cli(argv, None, self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("the token belongs to beta, this guild is alpha", err)
        self.assertFalse(paths.realm_config_path().exists())

    def test_join_rejects_a_malformed_whoami(self):
        self._name_guild("alpha")
        for payload in ({"member": "alpha"}, {"member": "alpha", "realm": "../x"}, {"member": 1, "realm": "r"}):
            with (
                mock.patch("getpass.getpass", return_value="t"),
                mock.patch.object(client, "request", return_value=payload),
            ):
                with self.assertRaises(GuildError):
                    realm_commands.join(self.url, self.fingerprint, False, None)
        self.assertFalse(paths.realm_config_path().exists())

    def test_join_does_not_echo_an_invalid_member(self):
        self._name_guild("alpha")
        payload = {"member": "\x1b[31mevil\n", "realm": "hearth"}
        with (
            mock.patch("getpass.getpass", return_value="t"),
            mock.patch.object(client, "request", return_value=payload),
        ):
            with self.assertRaises(GuildError) as raised:
                realm_commands.join(self.url, self.fingerprint, False, None)
        self.assertEqual(raised.exception.message, "realm hub sent an invalid response")

    def test_hub_error_text_is_stripped_and_capped(self):
        config = {
            "url": self.url,
            "fingerprint": self.fingerprint,
            "guild": "alpha",
            "realm": "test-realm",
            "token": "nope",
        }
        hostile = "\x1b[31mred\nline\x7f\x85" + "x" * 500

        class Reply:
            status = 400

            def getheader(self, name):
                return None

            def read(self, limit):
                return json.dumps({"error": hostile}).encode("utf-8")

        with mock.patch.object(http.client.HTTPSConnection, "getresponse", return_value=Reply()):
            with self.assertRaises(GuildError) as raised:
                client.request(config, "GET", "/status", None)
        message = raised.exception.message
        self.assertNotRegex(message, r"[\x00-\x1f\x7f-\x9f]")
        self.assertLessEqual(len(message), len("realm hub refused (400): ") + 200)

    def test_status_with_an_invalid_realm_is_an_invalid_response(self):
        self._join("alpha", [])
        for realm in ("\x1b[31m", "../x", 3, None):
            with mock.patch.object(client, "request", return_value={"realm": realm, "guilds": []}):
                with self.assertRaises(GuildError) as raised:
                    realm_commands.realm_status_model(self._ctx())
            self.assertEqual(raised.exception.message, "realm hub sent an invalid response")
        self.assertFalse(paths.realm_cache_path().exists())

    def test_status_with_a_renamed_realm_asks_to_rejoin(self):
        self._join("alpha", [])
        with mock.patch.object(client, "request", return_value={"realm": "other", "guilds": []}):
            with self.assertRaises(GuildError) as raised:
                realm_commands.realm_status_model(self._ctx())
        self.assertEqual(
            raised.exception.message,
            "the hub now calls its realm other, this guild joined test-realm: re-run join --force",
        )
        self.assertFalse(paths.realm_cache_path().exists())

    def test_cache_with_an_invalid_realm_is_malformed(self):
        paths.realm_cache_path().parent.mkdir(parents=True, exist_ok=True)
        paths.realm_cache_path().write_text(
            '{"fetched_at": "2026-10-24T10:00:00+00:00", "realm": "\\u001b[31m", "guilds": []}'
        )
        with self.assertRaises(GuildError) as raised:
            realm_commands.cached_status_model()
        self.assertIn("malformed", raised.exception.message)
        self.assertNotIn("\x1b", raised.exception.message)

    def _ctx(self):
        return mock.Mock(now=timeutil.utcnow())

    def test_join_with_wrong_token_keeps_no_file(self):
        self._name_guild("alpha")
        argv = ["realm", "join", self.url, "--fingerprint", self.fingerprint]
        with mock.patch("getpass.getpass", return_value="wrong"):
            code, out, err = self.run_cli(argv, None, self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("401", err)
        self.assertFalse(paths.realm_config_path().exists())

    def test_join_rejects_bad_inputs(self):
        with mock.patch("getpass.getpass", return_value="t"):
            self._name_guild("alpha")
            for url, fingerprint in (
                ("http://127.0.0.1:1", self.fingerprint),
                (self.url + "/x", self.fingerprint),
                (self.url, "AA:BB"),
            ):
                with self.assertRaises(GuildError):
                    realm_commands.join(url, fingerprint, False, None)
        with mock.patch("getpass.getpass", return_value="  "):
            with self.assertRaises(GuildError):
                realm_commands.join(self.url, self.fingerprint, False, None)

    def test_fingerprint_mismatch_sends_nothing(self):
        wrong = ":".join(["00"] * 32)
        config = {
            "url": self.url,
            "fingerprint": wrong,
            "guild": "alpha",
            "realm": "test-realm",
            "token": self.tokens["alpha"],
        }
        with mock.patch.object(http.client.HTTPSConnection, "request") as sent:
            with self.assertRaises(GuildError) as raised:
                client.request(config, "GET", "/status", None)
        sent.assert_not_called()
        self.assertIn(
            "fingerprint mismatch: expected {}, got {}".format(wrong, self.fingerprint), raised.exception.message
        )

    def _serve(self, wrap):
        return realm_hub_fixture.serve_once(self, wrap)

    def _assert_tls_refused(self, url):
        config = {
            "url": url,
            "fingerprint": self.fingerprint,
            "guild": "alpha",
            "realm": "test-realm",
            "token": self.tokens["alpha"],
        }
        with mock.patch.object(http.client.HTTPSConnection, "request") as sent:
            with self.assertRaises(GuildError) as raised:
                client.request(config, "GET", "/status", None)
        sent.assert_not_called()
        self.assertEqual(
            "realm hub refused the TLS 1.3 handshake (downgrade or not a realm hub)", raised.exception.message
        )

    def test_tls12_only_hub_is_refused_before_the_token_is_sent(self):
        hub_config = hubconfig.load()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(hub_config["cert"], hub_config["key"])
        self._assert_tls_refused(self._serve(lambda peer: context.wrap_socket(peer, server_side=True)))

    def test_plain_http_peer_is_refused_before_the_token_is_sent(self):
        self._assert_tls_refused(self._serve(lambda peer: peer.sendall(b"HTTP/1.0 400 Bad Request\r\n\r\n")))

    def test_unreachable_hub_is_a_guild_error(self):
        config = {
            "url": "https://127.0.0.1:1",
            "fingerprint": self.fingerprint,
            "guild": "alpha",
            "realm": "test-realm",
            "token": "t",
        }
        with self.assertRaises(GuildError) as raised:
            client.request(config, "GET", "/status", None)
        self.assertIn("realm hub unreachable: ", raised.exception.message)

    def test_oversize_response_is_refused(self):
        config = {
            "url": self.url,
            "fingerprint": self.fingerprint,
            "guild": "alpha",
            "realm": "test-realm",
            "token": self.tokens["alpha"],
        }
        with mock.patch.object(client, "MAX_RESPONSE_BYTES", 5):
            with self.assertRaises(GuildError) as raised:
                client.request(config, "GET", "/status", None)
        self.assertIn("too large", raised.exception.message)

    def test_push_then_status_shows_counts(self):
        self._seed()
        self._join("alpha", [])
        code, out, err = self.run_cli(["realm", "push"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("2 project(s)", out)
        code, out, err = self.run_cli(["realm", "status"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("realm test-realm", out)
        self.assertIn("alpha (last seen", out)
        self.assertIn("acme: parties 1, quests 1, PRs 2 (1 ready), asks 1, main red", out)
        self.assertIn("idle: parties 0, quests 0, PRs 0 (0 ready), asks 0", out)
        self.assertNotIn("idle: parties 0, quests 0, PRs 0 (0 ready), asks 0, main red", out)
        self.assertEqual(stat.S_IMODE(paths.realm_cache_path().stat().st_mode), 0o600)

    def test_cached_status_works_offline(self):
        self._join("alpha", [])
        self.run_cli(["realm", "push"], None, self.root)
        self.assertEqual(self.run_cli(["realm", "status"], None, self.root)[0], 0)
        self.server.shutdown()
        self.server.server_close()
        code, out, err = self.run_cli(["realm", "status", "--cached"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("alpha (last seen", out)
        self.assertNotEqual(self.run_cli(["realm", "status"], None, self.root)[0], 0)

    def test_cached_without_cache_or_malformed_fails(self):
        with self.assertRaises(GuildError):
            realm_commands.cached_status_model()
        paths.realm_cache_path().parent.mkdir(parents=True, exist_ok=True)
        paths.realm_cache_path().write_text('{"fetched_at": "x"}')
        with self.assertRaises(GuildError):
            realm_commands.cached_status_model()
        paths.realm_cache_path().write_text('{"fetched_at": "2026-10-24T10:00:00+00:00", "guilds": []}')
        with self.assertRaises(GuildError):
            realm_commands.cached_status_model()
        paths.realm_cache_path().write_text('{"fetched_at": "2026-10-24T10:00:00+00:00", "realm": 3, "guilds": []}')
        with self.assertRaises(GuildError):
            realm_commands.cached_status_model()

    def test_cache_carries_the_realm(self):
        self._join("alpha", [])
        self.run_cli(["realm", "status"], None, self.root)
        self.assertEqual(json.loads(paths.realm_cache_path().read_text())["realm"], "test-realm")
        self.assertEqual(realm_commands.cached_status_model()["realm"], "test-realm")

    def test_config_without_realm_asks_to_rejoin(self):
        self._join("alpha", [])
        saved = json.loads(paths.realm_config_path().read_text())
        del saved["realm"]
        paths.realm_config_path().write_text(json.dumps(saved))
        code, out, err = self.run_cli(["realm", "status"], None, self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("join --force", err)
        self.assertIn("join --force", realm_checks.config_lines()[-1][1])

    def test_invalid_entries_are_dropped_and_reported(self):
        self._join("alpha", [])
        good = {
            "guild": "beta",
            "generated_at": "2026-10-24T10:00:00+00:00",
            "received_at": "2026-10-24T10:00:00+00:00",
            "projects": [],
        }
        payload = {"realm": "test-realm", "guilds": [good, {"guild": "evil", "projects": "x"}]}
        with mock.patch.object(client, "request", return_value=payload):
            code, out, err = self.run_cli(["realm", "status"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("dropped 1 invalid entry", out)
        self.assertIn("beta", out)
        self.assertNotIn("evil", out)
        with mock.patch.object(client, "request", return_value={"realm": "test-realm", "guilds": "nope"}):
            self.assertNotEqual(self.run_cli(["realm", "status"], None, self.root)[0], 0)
        with mock.patch.object(client, "request", return_value={"guilds": []}):
            self.assertNotEqual(self.run_cli(["realm", "status"], None, self.root)[0], 0)

    def test_claudecode_refuses_join_and_push_but_not_status(self):
        os.environ["CLAUDECODE"] = "1"
        self.assertNotEqual(self._join("alpha", [])[0], 0)
        self.assertFalse(paths.realm_config_path().exists())
        os.environ.pop("CLAUDECODE")
        self._join("alpha", [])
        os.environ["CLAUDECODE"] = "1"
        code, out, err = self.run_cli(["realm", "push"], None, self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("for the human", err)
        os.environ.pop("CLAUDECODE")
        self.run_cli(["realm", "push"], None, self.root)
        os.environ["CLAUDECODE"] = "1"
        self.assertEqual(self.run_cli(["realm", "status"], None, self.root)[0], 0)

    def test_push_without_join_fails(self):
        code, out, err = self.run_cli(["realm", "push"], None, self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("realm join", err)

    def test_malformed_config_is_refused(self):
        paths.realm_config_path().parent.mkdir(parents=True, exist_ok=True)
        paths.realm_config_path().write_text("{nope")
        with self.assertRaises(GuildError):
            clientconfig.load()
        paths.realm_config_path().write_text('{"url": "http://x"}')
        with self.assertRaises(GuildError):
            clientconfig.load()

    def test_doctor_reports_bad_mode_and_shape(self):
        self.assertEqual(realm_checks.config_lines(), [])
        self._join("alpha", [])
        self.assertEqual(realm_checks.config_lines(), [(True, "ok      realm config")])
        paths.realm_config_path().chmod(0o644)
        lines = realm_checks.config_lines()
        self.assertFalse(lines[0][0])
        self.assertIn("mode must be 0600", lines[0][1])
        paths.realm_config_path().write_text('{"url": 1}')
        self.assertFalse(realm_checks.config_lines()[-1][0])
        paths.realm_config_path().write_text("{nope")
        self.assertIn("not valid JSON", realm_checks.config_lines()[-1][1])

    def test_snapshot_is_valid_status(self):
        self._seed()
        self._join("alpha", [])
        conn = db.connect(paths.db_path())
        try:
            ctx = RunContext(
                conn,
                None,
                self.root,
                timeutil.utcnow(),
                "t@h",
                self.sessions_dir,
                self.config_home / "guild" / "projects",
                self.state_home,
            )
            body = snapshot.build(ctx, "alpha")
        finally:
            conn.close()
        status.validate(body, False)
        by_name = {project["name"]: project for project in body["projects"]}
        self.assertEqual(by_name["acme"]["open_prs"], 2)
        self.assertFalse(by_name["idle"]["main_red"])


if __name__ == "__main__":
    unittest.main()
