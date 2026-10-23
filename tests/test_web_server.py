import os
import contextlib
import http.client
import io
import json
import shutil
import tempfile
import threading
from pathlib import Path
from unittest import mock

from guild import webserver
from tests.testutil import GuildTestCase


class WebServerTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.server = webserver.start(0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        super().tearDown()

    def _connection(self):
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)

    def _get(self, path, host):
        conn = self._connection()
        conn.request("GET", path, headers={"Host": host})
        response = conn.getresponse()
        body = response.read()
        conn.close()
        return response, body


class RouteTests(WebServerTestCase):
    def _host(self):
        return "127.0.0.1:{}".format(self.port)

    def test_root_serves_index_html(self):
        response, body = self._get("/", self._host())
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/html; charset=utf-8")
        self.assertIn(b"<!DOCTYPE html>", body)

    def test_app_js_served_as_javascript(self):
        response, body = self._get("/app.js", self._host())
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/javascript; charset=utf-8")
        self.assertTrue(body)

    def test_app_css_served_as_css(self):
        response, body = self._get("/app.css", self._host())
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/css; charset=utf-8")
        self.assertTrue(body)

    def test_unknown_path_is_404(self):
        response, body = self._get("/nope", self._host())
        self.assertEqual(response.status, 404)

    def test_localhost_host_header_is_also_accepted(self):
        response, body = self._get("/", "localhost:{}".format(self.port))
        self.assertEqual(response.status, 200)

    def test_wrong_host_header_is_rejected(self):
        response, body = self._get("/", "evil.example")
        self.assertIn(response.status, (421, 403))

    def test_missing_host_header_is_rejected(self):
        conn = self._connection()
        conn.putrequest("GET", "/", skip_host=True)
        conn.endheaders()
        response = conn.getresponse()
        response.read()
        conn.close()
        self.assertIn(response.status, (421, 403))

    def test_post_is_405(self):
        conn = self._connection()
        conn.request("POST", "/api/board", headers={"Host": self._host()})
        response = conn.getresponse()
        response.read()
        conn.close()
        self.assertEqual(response.status, 405)

    def test_put_patch_delete_and_head_are_405(self):
        for method in ("PUT", "PATCH", "DELETE", "HEAD"):
            with self.subTest(method=method):
                conn = self._connection()
                conn.request(method, "/", headers={"Host": self._host()})
                response = conn.getresponse()
                response.read()
                conn.close()
                self.assertEqual(response.status, 405)

    def test_malformed_request_line_is_logged_as_a_server_error(self):
        import socket

        stderr_capture = io.StringIO()
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        with contextlib.redirect_stderr(stderr_capture):
            sock.sendall(b"not a valid http request line at all\r\n\r\n")
            response = sock.recv(4096)
        sock.close()
        self.assertIn(b"400", response)
        self.assertIn("guild web:", stderr_capture.getvalue())


class SecurityHeaderTests(WebServerTestCase):
    def _assert_security_headers(self, response):
        self.assertEqual(
            response.getheader("Content-Security-Policy"),
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.getheader("Referrer-Policy"), "no-referrer")

    def test_security_headers_on_index(self):
        response, body = self._get("/", "127.0.0.1:{}".format(self.port))
        self._assert_security_headers(response)

    def test_security_headers_on_api(self):
        response, body = self._get("/api/board", "127.0.0.1:{}".format(self.port))
        self._assert_security_headers(response)

    def test_no_store_only_on_api(self):
        api_response, _ = self._get("/api/board", "127.0.0.1:{}".format(self.port))
        self.assertEqual(api_response.getheader("Cache-Control"), "no-store")
        index_response, _ = self._get("/", "127.0.0.1:{}".format(self.port))
        self.assertIsNone(index_response.getheader("Cache-Control"))


class BoardEndpointTests(WebServerTestCase):
    def test_board_json_shape(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        self.write_session(os.getpid(), "sess-1", "alpha-g1")

        response, body = self._get("/api/board", "127.0.0.1:{}".format(self.port))
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/json; charset=utf-8")
        payload = json.loads(body)
        self.assertEqual(set(payload), {"generated_at", "asks", "notices", "ideas", "adventurers", "health_jobs", "memory", "new_notice_count", "parties", "drift", "raids", "merge_queues", "ready_for_you", "blocked", "projects", "project_names", "quest_boards"})
        self.assertEqual([party["name"] for party in payload["parties"]], ["alpha"])
        self.assertEqual(payload["parties"][0]["status"]["name"], "unknown")
        self.assertEqual(payload["blocked"], [])


class _HungUpClient:
    def write(self, data):
        raise BrokenPipeError(32, "Broken pipe")


class ClientHangUpTests(GuildTestCase):
    def test_a_client_that_hung_up_is_not_an_error(self):
        handler = webserver.BoardRequestHandler.__new__(webserver.BoardRequestHandler)
        handler.request_version = "HTTP/1.1"
        handler.requestline = "GET /api/board HTTP/1.1"
        handler.command = "GET"
        handler.client_address = ("127.0.0.1", 0)
        handler.wfile = _HungUpClient()
        handler._write(200, b"{}", "application/json", "no-store")


class ServeForeverTests(GuildTestCase):
    def test_prints_url_and_returns_0_on_keyboard_interrupt(self):
        stdout = io.StringIO()
        with mock.patch("http.server.ThreadingHTTPServer.serve_forever", side_effect=KeyboardInterrupt):
            with contextlib.redirect_stdout(stdout):
                exit_code = webserver.serve_forever(0)
        self.assertEqual(exit_code, 0)
        self.assertRegex(stdout.getvalue(), r"guild web: http://127\.0\.0\.1:\d+/\n")


class CliWiringTests(GuildTestCase):
    def test_web_command_delegates_to_webserver(self):
        with mock.patch("guild.commands.web.webserver.serve_forever", return_value=0) as mocked:
            code, out, err = self.run_cli(["web", "--port", "0"], None, None)
        self.assertEqual(code, 0)
        mocked.assert_called_once_with(0)

    def test_port_defaults_to_8765(self):
        with mock.patch("guild.commands.web.webserver.serve_forever", return_value=0) as mocked:
            code, out, err = self.run_cli(["web"], None, None)
        self.assertEqual(code, 0)
        mocked.assert_called_once_with(8765)


if __name__ == "__main__":
    import unittest

    unittest.main()


class StaticSnapshotTests(GuildTestCase):
    def test_static_files_are_served_from_start_time_snapshot(self):
        web_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, web_dir)
        shutil.copytree(webserver._WEB_DIR, web_dir, dirs_exist_ok=True)
        original = (web_dir / "app.js").read_bytes()
        patcher = mock.patch.object(webserver, "_WEB_DIR", web_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        server = webserver.start(0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        (web_dir / "app.js").write_bytes(b"changed")
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/app.js", headers={"Host": "127.0.0.1:{}".format(port)})
        body = conn.getresponse().read()
        conn.close()
        self.assertEqual(body, original)
