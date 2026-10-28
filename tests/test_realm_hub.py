import contextlib
import http.client
import io
import json
import os
import shutil
import socket
import ssl
import unittest
import unittest.mock
from unittest import mock

from guild import names, paths
from guild.commands import realm as realm_commands
from guild.errors import GuildError
from guild.realm import hub, hubconfig, pin, status
from tests import realm_hub_fixture
from tests.testutil import GuildTestCase

_NOW = "2026-10-24T10:00:00+00:00"
_HUMAN = None


def _status_body(guild):
    return {
        "guild": guild,
        "generated_at": _NOW,
        "projects": [
            {
                "name": "acme",
                "parties": 1,
                "open_quests": 2,
                "open_prs": 3,
                "ready_prs": 1,
                "open_asks": 0,
                "main_red": False,
            }
        ],
    }


@unittest.skipUnless(shutil.which("openssl"), "openssl not on PATH")
class RealmHubTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.server, self.cert, self.tokens = realm_hub_fixture.start_hub(self)
        self.port = self.server.server_address[1]

    def _request(self, method, path, token, body, content_type="application/json", raw=None):
        context = ssl.create_default_context(cafile=self.cert)
        context.check_hostname = False
        connection = http.client.HTTPSConnection("127.0.0.1", self.port, context=context, timeout=10)
        headers = {}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        payload = raw
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
        if payload is not None:
            headers["Content-Type"] = content_type
        try:
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()

    def _as(self, member, method, path, body=None, **kwargs):
        return self._request(method, path, self.tokens[member], body, **kwargs)

    def test_unknown_token_is_401(self):
        self.assertEqual(self._request("GET", "/status", "nope", None)[0], 401)
        self.assertEqual(self._request("GET", "/status", None, None)[0], 401)

    def test_status_roundtrip_adds_received_at(self):
        self.assertEqual(self._as("alpha", "PUT", "/status", _status_body("alpha"))[0], 200)
        self.assertEqual(self._as("beta", "PUT", "/status", _status_body("beta"))[0], 200)
        code, payload = self._as("beta", "GET", "/status")
        self.assertEqual(code, 200)
        self.assertEqual([entry["guild"] for entry in payload["guilds"]], ["alpha", "beta"])
        self.assertEqual(payload["realm"], "test-realm")
        status.validate(payload["guilds"][0], True)

    def test_whoami_names_the_member_and_the_realm(self):
        self.assertEqual(self._as("beta", "GET", "/whoami"), (200, {"member": "beta", "realm": "test-realm"}))
        self.assertEqual(self._request("GET", "/whoami", "nope", None)[0], 401)

    def test_status_for_other_guild_is_403(self):
        self.assertEqual(self._as("alpha", "PUT", "/status", _status_body("beta"))[0], 403)

    def test_status_bad_schema_is_400(self):
        body = _status_body("alpha")
        body["projects"][0]["parties"] = True
        self.assertEqual(self._as("alpha", "PUT", "/status", body)[0], 400)
        body = _status_body("alpha")
        body["extra"] = "x"
        self.assertEqual(self._as("alpha", "PUT", "/status", body)[0], 400)

    def test_status_oversize_is_413(self):
        body = _status_body("alpha")
        body["projects"] = body["projects"] * 400
        self.assertEqual(self._as("alpha", "PUT", "/status", body)[0], 413)

    def test_bad_json_and_content_type(self):
        self.assertEqual(self._as("alpha", "PUT", "/status", None, raw=b"{nope")[0], 400)
        self.assertEqual(self._as("alpha", "PUT", "/status", None, raw=b"[1]")[0], 400)
        self.assertEqual(self._as("alpha", "PUT", "/status", None, raw=b"{}", content_type="text/plain")[0], 415)

    def test_unknown_route_and_method(self):
        self.assertEqual(self._as("alpha", "GET", "/nope")[0], 404)
        self.assertEqual(self._as("alpha", "POST", "/status", {})[0], 405)
        self.assertEqual(self._as("alpha", "PATCH", "/status")[0], 405)

    def test_inbox_send_fetch_delete(self):
        code, sent = self._as("alpha", "POST", "/inbox/beta", {"name": "req.md", "content": "héllo"})
        self.assertEqual(code, 201)
        file_id = sent["id"]
        self.assertRegex(file_id, r"^[0-9a-f]{16}$")
        code, listing = self._as("beta", "GET", "/inbox")
        self.assertEqual([meta["id"] for meta in listing["files"]], [file_id])
        self.assertEqual(listing["files"][0]["from"], "alpha")
        code, fetched = self._as("beta", "GET", "/inbox/" + file_id)
        self.assertEqual((code, fetched["content"], fetched["size"]), (200, "héllo", 6))
        self.assertEqual(self._as("beta", "DELETE", "/inbox/" + file_id)[0], 200)
        self.assertEqual(self._as("beta", "GET", "/inbox/" + file_id)[0], 404)
        self.assertEqual(self._as("beta", "DELETE", "/inbox/" + file_id)[0], 404)

    def test_inbox_is_isolated_per_member(self):
        file_id = self._as("alpha", "POST", "/inbox/beta", {"name": "a", "content": "x"})[1]["id"]
        self.assertEqual(self._as("alpha", "GET", "/inbox/" + file_id)[0], 404)
        self.assertEqual(self._as("alpha", "DELETE", "/inbox/" + file_id)[0], 404)
        self.assertEqual(self._as("alpha", "GET", "/inbox")[1]["files"], [])

    def test_inbox_unknown_target_and_bad_id(self):
        self.assertEqual(self._as("alpha", "POST", "/inbox/ghost", {"name": "a", "content": "x"})[0], 404)
        self.assertEqual(self._as("alpha", "GET", "/inbox/..%2f..%2fconfig")[0], 404)
        self.assertEqual(self._as("alpha", "GET", "/inbox/ABCDEF0123456789")[0], 404)

    def test_inbox_name_is_sanitized(self):
        cases = {
            "../../etc/passwd": "etc-passwd.md",
            "..\\..\\x.MD": "x.md",
            "": "request.md",
            "///": "request.md",
            "plan.v2.md": "plan-v2.md",
        }
        for raw_name, expected in cases.items():
            file_id = self._as("alpha", "POST", "/inbox/beta", {"name": raw_name, "content": "x"})[1]["id"]
            self.assertEqual(self._as("beta", "GET", "/inbox/" + file_id)[1]["name"], expected)

    def test_inbox_rejects_bad_bodies(self):
        self.assertEqual(self._as("alpha", "POST", "/inbox/beta", {"name": "a"})[0], 400)
        self.assertEqual(self._as("alpha", "POST", "/inbox/beta", {"name": 1, "content": "x"})[0], 400)
        self.assertEqual(self._as("alpha", "POST", "/inbox/beta", {"name": "a", "content": "x", "from": "z"})[0], 400)
        big = {"name": "a", "content": "x" * (hub.CONTENT_MAX_BYTES + 1)}
        self.assertEqual(self._as("alpha", "POST", "/inbox/beta", big)[0], 413)

    def _add_senders(self, count):
        for index in range(count):
            name = "sender{}".format(index)
            self.tokens[name] = realm_hub_fixture.token_of(realm_commands.member_add(name, _HUMAN))

    def test_inbox_total_cap_is_507(self):
        self._add_senders(6)
        message = {"name": "a", "content": "x"}
        for index in range(5):
            for _ in range(hub.INBOX_MAX_PER_SENDER):
                self.assertEqual(self._as("sender{}".format(index), "POST", "/inbox/beta", message)[0], 201)
        self.assertEqual(self._as("sender5", "POST", "/inbox/beta", message)[0], 507)

    def test_inbox_per_sender_cap_is_507(self):
        message = {"name": "a", "content": "x"}
        for _ in range(hub.INBOX_MAX_PER_SENDER):
            self.assertEqual(self._as("alpha", "POST", "/inbox/beta", message)[0], 201)
        self.assertEqual(self._as("alpha", "POST", "/inbox/beta", message)[0], 507)
        self._add_senders(1)
        self.assertEqual(self._as("sender0", "POST", "/inbox/beta", message)[0], 201)

    def test_deeply_nested_json_is_400(self):
        self.assertEqual(self._as("alpha", "PUT", "/status", None, raw=b"[" * 16000)[0], 400)

    def test_readded_member_inherits_nothing(self):
        self._as("beta", "POST", "/inbox/alpha", {"name": "a", "content": "x"})
        realm_commands.member_remove("alpha", _HUMAN)
        self.assertFalse((paths.realm_hub_store_dir() / "inbox" / "alpha").exists())
        self.tokens["alpha"] = realm_hub_fixture.token_of(realm_commands.member_add("alpha", _HUMAN))
        self.assertEqual(self._as("alpha", "GET", "/inbox")[1]["files"], [])

    def test_connection_gate_drops_when_full(self):
        slots = [self.server.connection_slots.acquire() for _ in range(hub.MAX_CONNECTIONS)]
        with mock.patch.object(self.server, "shutdown_request") as shutdown:
            self.server.process_request(object(), ("127.0.0.1", 1))
        shutdown.assert_called_once()
        for _ in slots:
            self.server.connection_slots.release()

    def _stall(self, send_headers):
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        self.addCleanup(sock.close)
        if send_headers:
            sock.sendall(b"\x16")
        return sock

    def _closed_within(self, sock, seconds):
        sock.settimeout(seconds)
        try:
            return sock.recv(1) == b""
        except ConnectionResetError:
            return True
        except socket.timeout:
            return False

    def test_stalled_connection_is_closed_at_the_deadline(self):
        with mock.patch.object(hub, "PRE_AUTH_DEADLINE_SECONDS", 0.5):
            silent = self._stall(False)
            dribbling = self._stall(True)
            self.assertTrue(self._closed_within(silent, 5))
            self.assertTrue(self._closed_within(dribbling, 5))

    def test_stalled_connections_free_their_slots_for_a_real_request(self):
        with mock.patch.object(hub, "PRE_AUTH_DEADLINE_SECONDS", 0.5):
            stalled = [self._stall(False) for _ in range(hub.MAX_CONNECTIONS)]
            for sock in stalled:
                self.assertTrue(self._closed_within(sock, 5))
            self.assertEqual(self._as("alpha", "GET", "/whoami")[0], 200)

    def test_client_capped_at_tls12_is_refused(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        connection = http.client.HTTPSConnection("127.0.0.1", self.port, context=context, timeout=10)
        try:
            with self.assertRaises(ssl.SSLError):
                connection.connect()
        finally:
            connection.close()

    def test_handle_error_is_quiet_for_tls_and_connection_errors(self):
        for error in (ssl.SSLError("x"), ConnectionResetError(), TimeoutError()):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                try:
                    raise error
                except OSError:
                    self.server.handle_error(None, ("127.0.0.1", 1))
            self.assertEqual(stderr.getvalue(), "")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            try:
                raise KeyError("secret")
            except KeyError:
                self.server.handle_error(None, ("127.0.0.1", 1))
        self.assertEqual(len(stderr.getvalue().splitlines()), 1)
        self.assertNotIn("secret", stderr.getvalue())

    def test_atomic_write_leaves_only_target(self):
        target = paths.realm_hub_store_dir() / "status" / "probe.json"
        hubconfig.write_atomic(target, b"1")
        hubconfig.write_atomic(target, b"2")
        self.assertEqual(os.listdir(target.parent), ["probe.json"])
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_removed_member_token_stops_working(self):
        self._as("alpha", "PUT", "/status", _status_body("alpha"))
        realm_commands.member_remove("alpha", _HUMAN)
        self.assertEqual(self._as("alpha", "GET", "/status")[0], 401)
        self.assertEqual(self._as("beta", "GET", "/status")[1]["guilds"], [])

    def test_store_and_config_modes(self):
        self.assertEqual(paths.realm_hub_config_path().stat().st_mode & 0o777, 0o600)
        self.assertEqual(paths.realm_hub_store_dir().stat().st_mode & 0o777, 0o700)
        key = paths.realm_hub_pki_dir() / "key.pem"
        self.assertEqual(key.stat().st_mode & 0o777, 0o600)
        config_text = paths.realm_hub_config_path().read_text()
        for token in self.tokens.values():
            self.assertNotIn(token, config_text)


@unittest.skipUnless(shutil.which("openssl"), "openssl not on PATH")
class RealmCommandTests(GuildTestCase):
    def test_init_refuses_twice_and_prints_fingerprint(self):
        output = realm_commands.init("test-realm", "127.0.0.1", 8443, _HUMAN)
        self.assertRegex(output, r"(?:[0-9A-F]{2}:){31}[0-9A-F]{2}")
        with self.assertRaises(GuildError):
            realm_commands.init("test-realm", "127.0.0.1", 8443, _HUMAN)
        self.assertIn(pin.cert_fingerprint(hubconfig.load()["cert"]), output)

    def test_init_without_openssl_fails_clearly(self):
        with unittest.mock.patch("shutil.which", return_value=None):
            with self.assertRaises(GuildError) as raised:
                realm_commands.init("test-realm", "127.0.0.1", 8443, _HUMAN)
        self.assertIn("openssl", raised.exception.message)
        self.assertFalse(hubconfig.exists())

    def test_init_requires_a_valid_realm_name(self):
        with self.assertRaises(GuildError):
            realm_commands.init("../x", "127.0.0.1", 8443, _HUMAN)
        self.assertFalse(hubconfig.exists())
        code, out, err = self.run_cli(["realm", "init", "--bind", "127.0.0.1", "--port", "8443"], None, self.root)
        self.assertNotEqual(code, 0)
        self.assertFalse(hubconfig.exists())

    def test_init_stores_the_realm_name(self):
        realm_commands.init("test-realm", "127.0.0.1", 8443, _HUMAN)
        self.assertEqual(hubconfig.load()["name"], "test-realm")

    def test_hub_config_with_a_bad_name_says_how_to_fix_it(self):
        paths.realm_hub_config_path().parent.mkdir(parents=True, exist_ok=True)
        for text in ('{"members": {}}', '{"members": {}, "name": "../x"}', '{"members": {}, "name": 3}'):
            paths.realm_hub_config_path().write_text(text)
            with self.assertRaises(GuildError) as raised:
                hubconfig.load()
            self.assertEqual(
                raised.exception.message,
                'realm hub config {} needs a valid "name": add it by hand (init refuses to run twice)'.format(
                    paths.realm_hub_config_path()
                ),
            )

    def test_hub_config_without_name_is_malformed(self):
        paths.realm_hub_config_path().parent.mkdir(parents=True, exist_ok=True)
        paths.realm_hub_config_path().write_text('{"members": {}}')
        with self.assertRaises(GuildError):
            hubconfig.load()

    def _join_line(self, bind):
        config = hubconfig.load()
        config["bind"] = bind
        hubconfig.save(config)
        return realm_commands.member_add("alpha", _HUMAN).splitlines()[-1]

    def test_member_add_prints_the_join_line_without_the_token(self):
        realm_commands.init("test-realm", "10.1.2.3", 8443, _HUMAN)
        output = realm_commands.member_add("alpha", _HUMAN)
        token = realm_hub_fixture.token_of(output)
        line = output.splitlines()[-1]
        self.assertEqual(
            line,
            "join on the guild with: guild realm join https://10.1.2.3:8443 --fingerprint {}".format(
                pin.cert_fingerprint(hubconfig.load()["cert"])
            ),
        )
        self.assertNotIn(token, line)

    def test_member_add_join_line_uses_placeholder_for_wildcard_binds(self):
        realm_commands.init("test-realm", "0.0.0.0", 8443, _HUMAN)
        self.assertIn("https://<hub-address>:8443 ", self._join_line("0.0.0.0"))
        realm_commands.member_remove("alpha", _HUMAN)
        self.assertIn("https://<hub-address>:8443 ", self._join_line("::"))

    def test_member_add_join_line_brackets_ipv6(self):
        realm_commands.init("test-realm", "::1", 8443, _HUMAN)
        self.assertIn("https://[::1]:8443 ", realm_commands.member_add("alpha", _HUMAN).splitlines()[-1])

    def test_init_rejects_bad_port_and_bind(self):
        for bind, port in (("127.0.0.1", 0), ("127.0.0.1", 70000), ("", 8443)):
            with self.assertRaises(GuildError):
                realm_commands.init("test-realm", bind, port, _HUMAN)

    def test_fingerprint_format(self):
        self.assertEqual(
            pin.fingerprint(b""),
            "E3:B0:C4:42:98:FC:1C:14:9A:FB:F4:C8:99:6F:B9:24:27:AE:41:E4:64:9B:93:4C:A4:95:99:1B:78:52:B8:55",
        )

    def test_member_commands(self):
        realm_commands.init("test-realm", "127.0.0.1", 8443, _HUMAN)
        output = realm_commands.member_add("alpha", _HUMAN)
        token = realm_hub_fixture.token_of(output)
        self.assertGreaterEqual(len(token), 43)
        self.assertEqual(hubconfig.load()["members"]["alpha"], hub.token_hash(token))
        with self.assertRaises(GuildError):
            realm_commands.member_add("alpha", _HUMAN)
        with self.assertRaises(GuildError):
            realm_commands.member_add("../x", _HUMAN)
        realm_commands.member_add("beta", _HUMAN)
        self.assertEqual(realm_commands.member_list(_HUMAN), ["alpha", "beta"])
        realm_commands.member_remove("alpha", _HUMAN)
        self.assertEqual(realm_commands.member_list(_HUMAN), ["beta"])
        with self.assertRaises(GuildError):
            realm_commands.member_remove("alpha", _HUMAN)

    def test_agent_environment_refuses_every_realm_command(self):
        realm_commands.init("test-realm", "127.0.0.1", 8443, _HUMAN)
        for args in (
            ["realm", "member", "add", "alpha"],
            ["realm", "member", "list"],
            ["realm", "member", "remove", "alpha"],
            ["realm", "init", "--name", "test-realm", "--bind", "127.0.0.1", "--port", "9"],
            ["realm", "serve"],
        ):
            with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
                code, out, err = self.run_cli(args, None, self.root)
            self.assertNotEqual(code, 0, args)
            self.assertIn("for the human", err)
        self.assertEqual(realm_commands.member_list(_HUMAN), [])

    def test_names_reject_trailing_newline(self):
        with self.assertRaises(GuildError):
            names.validate_name("x\n", "name")
        self.assertFalse(hub.is_file_id("0123456789abcdef\n"))
        self.assertTrue(hub.is_file_id("0123456789abcdef"))

    def test_cli_member_flow(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("CLAUDECODE", None)
        realm_commands.init("test-realm", "127.0.0.1", 8443, _HUMAN)
        code, out, err = self.run_cli(["realm", "member", "add", "alpha"], None, self.root)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["realm", "member", "list"], None, self.root)
        self.assertEqual(out.strip(), "alpha")

    def test_member_commands_need_config(self):
        with self.assertRaises(GuildError):
            realm_commands.member_list(_HUMAN)


class StatusSchemaTests(unittest.TestCase):
    def test_valid_and_received_at_expectation(self):
        body = _status_body("alpha")
        status.validate(body, False)
        with self.assertRaises(GuildError):
            status.validate(body, True)
        body["received_at"] = _NOW
        status.validate(body, True)
        with self.assertRaises(GuildError):
            status.validate(body, False)

    def test_rejects_bad_shapes(self):
        def mutated(change):
            body = _status_body("alpha")
            change(body)
            return body

        bad = [
            mutated(lambda b: b["projects"][0].pop("main_red")),
            mutated(lambda b: b["projects"][0].update(main_red=1)),
            mutated(lambda b: b["projects"][0].update(open_prs=-1)),
            mutated(lambda b: b["projects"][0].update(name="../x")),
            mutated(lambda b: b.update(generated_at="yesterday")),
            mutated(lambda b: b.update(guild="")),
            mutated(lambda b: b.update(projects=b["projects"] * 51)),
            mutated(lambda b: b.update(projects="x")),
            [],
        ]
        for body in bad:
            with self.assertRaises(GuildError):
                status.validate(body, False)
