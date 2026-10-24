import http.client
import json
import os
import shutil
import stat
import unittest
from unittest import mock

from guild import db, paths, timeutil
from guild.commands import doctor as doctor_commands
from guild.commands import realm as realm_commands
from guild.context import RunContext
from guild.errors import GuildError
from guild.realm import client, clientconfig, pin, snapshot, status
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

    def _join(self, member, extra):
        argv = ["realm", "join", self.url, "--fingerprint", self.fingerprint, "--guild", member] + extra
        with mock.patch("getpass.getpass", return_value=self.tokens[member]):
            return self.run_cli(argv, None, self.root)

    def _seed(self):
        self.register_project("acme", ["acme/app", "acme/lib"])
        self.register_project("idle", ["acme/idle"])
        conn = db.connect(paths.db_path())
        try:
            _insert(conn, "INSERT INTO parties (name, project, generation, state) VALUES ('p1', 'acme', 1, 'active')", ())
            _insert(conn, "INSERT INTO parties (name, project, generation, state) VALUES ('p2', 'acme', 1, 'closed')", ())
            _insert(conn, "INSERT INTO quests (slug, project, party, epic, title, state) VALUES ('q1', 'acme', 'p1', NULL, 't', 'active')", ())
            _insert(conn, "INSERT INTO quests (slug, project, party, epic, title, state) VALUES ('q2', 'acme', 'p1', NULL, 't', 'done')", ())
            for repo, number, lifecycle in (
                ("acme/app", 1, "ready"), ("acme/lib", 2, "draft"), ("acme/app", 3, "merged"), ("acme/idle", 4, "closed"),
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
            _insert(conn, "INSERT INTO main_status (repo, source, red, reason, updated_at) VALUES ('acme/lib', 'manual', 1, 'r', '2026-10-24T10:00:00+00:00')", ())
            _insert(conn, "INSERT INTO main_status (repo, source, red, reason, updated_at, external) VALUES ('acme/idle', 'gh', 1, 'billing', '2026-10-24T10:00:00+00:00', 'billing')", ())
        finally:
            conn.close()

    def test_join_writes_private_config_and_refuses_overwrite(self):
        code, out, err = self._join("alpha", [])
        self.assertEqual(code, 0, err)
        path = paths.realm_config_path()
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        saved = json.loads(path.read_text())
        self.assertEqual(saved["guild"], "alpha")
        self.assertEqual(saved["token"], self.tokens["alpha"])
        self.assertEqual(saved["fingerprint"], self.fingerprint)
        self.assertNotEqual(self._join("alpha", [])[0], 0)
        self.assertEqual(self._join("alpha", ["--force"])[0], 0)

    def test_join_with_wrong_token_keeps_no_file(self):
        argv = ["realm", "join", self.url, "--fingerprint", self.fingerprint, "--guild", "alpha"]
        with mock.patch("getpass.getpass", return_value="wrong"):
            code, out, err = self.run_cli(argv, None, self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("401", err)
        self.assertFalse(paths.realm_config_path().exists())

    def test_join_rejects_bad_inputs(self):
        with mock.patch("getpass.getpass", return_value="t"):
            for url, fingerprint, name in (
                ("http://127.0.0.1:1", self.fingerprint, "alpha"),
                (self.url + "/x", self.fingerprint, "alpha"),
                (self.url, "AA:BB", "alpha"),
                (self.url, self.fingerprint, "../x"),
            ):
                with self.assertRaises(GuildError):
                    realm_commands.join(url, fingerprint, name, False, None)
        with mock.patch("getpass.getpass", return_value="  "):
            with self.assertRaises(GuildError):
                realm_commands.join(self.url, self.fingerprint, "alpha", False, None)

    def test_fingerprint_mismatch_sends_nothing(self):
        wrong = ":".join(["00"] * 32)
        config = {"url": self.url, "fingerprint": wrong, "guild": "alpha", "token": self.tokens["alpha"]}
        with mock.patch.object(http.client.HTTPSConnection, "request") as sent:
            with self.assertRaises(GuildError) as raised:
                client.request(config, "GET", "/status", None)
        sent.assert_not_called()
        self.assertIn("fingerprint mismatch: expected {}, got {}".format(wrong, self.fingerprint), raised.exception.message)

    def test_unreachable_hub_is_a_guild_error(self):
        config = {"url": "https://127.0.0.1:1", "fingerprint": self.fingerprint, "guild": "alpha", "token": "t"}
        with self.assertRaises(GuildError):
            client.request(config, "GET", "/status", None)

    def test_oversize_response_is_refused(self):
        config = {"url": self.url, "fingerprint": self.fingerprint, "guild": "alpha", "token": self.tokens["alpha"]}
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

    def test_invalid_entries_are_dropped_and_reported(self):
        self._join("alpha", [])
        good = {
            "guild": "beta", "generated_at": "2026-10-24T10:00:00+00:00", "received_at": "2026-10-24T10:00:00+00:00",
            "projects": [],
        }
        payload = {"guilds": [good, {"guild": "evil", "projects": "x"}]}
        with mock.patch.object(client, "request", return_value=payload):
            code, out, err = self.run_cli(["realm", "status"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("dropped 1 invalid entry", out)
        self.assertIn("beta", out)
        self.assertNotIn("evil", out)
        with mock.patch.object(client, "request", return_value={"guilds": "nope"}):
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
        self.assertEqual(doctor_commands._realm_lines(), [])
        self._join("alpha", [])
        self.assertEqual(doctor_commands._realm_lines(), [(True, "ok      realm config")])
        paths.realm_config_path().chmod(0o644)
        lines = doctor_commands._realm_lines()
        self.assertFalse(lines[0][0])
        self.assertIn("mode must be 0600", lines[0][1])
        paths.realm_config_path().write_text('{"url": 1}')
        self.assertFalse(doctor_commands._realm_lines()[-1][0])
        paths.realm_config_path().write_text("{nope")
        self.assertIn("not valid JSON", doctor_commands._realm_lines()[-1][1])

    def test_snapshot_is_valid_status(self):
        self._seed()
        self._join("alpha", [])
        conn = db.connect(paths.db_path())
        try:
            ctx = RunContext(conn, None, self.root, timeutil.utcnow(), "t@h", self.sessions_dir,
                             self.config_home / "guild" / "projects", self.state_home)
            body = snapshot.build(ctx, "alpha")
        finally:
            conn.close()
        status.validate(body, False)
        by_name = {project["name"]: project for project in body["projects"]}
        self.assertEqual(by_name["acme"]["open_prs"], 2)
        self.assertFalse(by_name["idle"]["main_red"])


if __name__ == "__main__":
    unittest.main()
