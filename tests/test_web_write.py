import http.client
import json
import re

from tests.test_web_server import WebServerTestCase

_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{40,}")


class WebWriteTestCase(WebServerTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.run_cli(["inbox", "--since-last"], "sess-1", self.repo_dir)

    def _host(self):
        return "127.0.0.1:{}".format(self.port)

    def _origin(self):
        return "http://127.0.0.1:{}".format(self.port)

    def _token(self):
        response, body = self._get("/api/session", self._host())
        return json.loads(body)["token"]

    def _good_headers(self):
        return {
            "Host": self._host(),
            "Origin": self._origin(),
            "X-Guild-Token": self._token(),
            "Content-Type": "application/json",
        }

    def _post(self, path, headers, body):
        conn = self._connection()
        conn.request("POST", path, body=body, headers=headers)
        response = conn.getresponse()
        payload = response.read()
        conn.close()
        return response, payload

    def _post_json(self, path, headers, data):
        return self._post(path, headers, json.dumps(data).encode("utf-8"))

    def _answer(self, text):
        return self._post_json("/api/asks/1/answer", self._good_headers(), {"answer": text})

    def _error(self, payload):
        return json.loads(payload)["error"]

    def _ask_state(self):
        code, out, err = self.run_cli(["asks"], None, None)
        return out


class SessionEndpointTests(WebWriteTestCase):
    def test_returns_token_with_no_store_and_security_headers(self):
        response, body = self._get("/api/session", self._host())
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
        self.assertIn("default-src 'self'", response.getheader("Content-Security-Policy"))
        self.assertRegex(json.loads(body)["token"], _TOKEN_RE)

    def test_token_is_stable_within_one_server(self):
        self.assertEqual(self._token(), self._token())

    def test_bad_host_is_rejected(self):
        response, body = self._get("/api/session", "evil.example")
        self.assertEqual(response.status, 421)

    def test_token_absent_from_other_get_responses(self):
        token = self._token()
        for path in ("/", "/app.js", "/app.css", "/api/board"):
            with self.subTest(path=path):
                response, body = self._get(path, self._host())
                self.assertNotIn(token.encode("utf-8"), body)


class RejectionTests(WebWriteTestCase):
    def test_bad_host_is_421(self):
        headers = self._good_headers()
        headers["Host"] = "evil.example"
        response, payload = self._post_json("/api/asks/1/answer", headers, {"answer": "yes"})
        self.assertEqual(response.status, 421)

    def test_missing_origin_is_403(self):
        headers = self._good_headers()
        del headers["Origin"]
        response, payload = self._post_json("/api/asks/1/answer", headers, {"answer": "yes"})
        self.assertEqual(response.status, 403)
        self.assertIn("error", json.loads(payload))

    def test_wrong_origin_is_403(self):
        for origin in ("http://evil.example", "https://127.0.0.1:{}".format(self.port), "null"):
            with self.subTest(origin=origin):
                headers = self._good_headers()
                headers["Origin"] = origin
                response, payload = self._post_json("/api/asks/1/answer", headers, {"answer": "yes"})
                self.assertEqual(response.status, 403)

    def test_localhost_origin_is_accepted(self):
        headers = self._good_headers()
        headers["Origin"] = "http://localhost:{}".format(self.port)
        response, payload = self._post_json("/api/asks/1/answer", headers, {"answer": "yes"})
        self.assertEqual(response.status, 200)

    def test_missing_token_is_403(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._post_json("/api/asks/1/answer", headers, {"answer": "yes"})
        self.assertEqual(response.status, 403)

    def test_wrong_token_is_403(self):
        headers = self._good_headers()
        headers["X-Guild-Token"] = "wrong"
        response, payload = self._post_json("/api/asks/1/answer", headers, {"answer": "yes"})
        self.assertEqual(response.status, 403)

    def test_non_ascii_token_is_403(self):
        headers = self._good_headers()
        headers["X-Guild-Token"] = "tökén"
        response, payload = self._post_json("/api/asks/1/answer", headers, {"answer": "yes"})
        self.assertEqual(response.status, 403)

    def test_wrong_content_type_is_415(self):
        for content_type in ("text/plain", "application/x-www-form-urlencoded"):
            with self.subTest(content_type=content_type):
                headers = self._good_headers()
                headers["Content-Type"] = content_type
                response, payload = self._post_json("/api/asks/1/answer", headers, {"answer": "yes"})
                self.assertEqual(response.status, 415)

    def test_missing_content_type_is_415(self):
        headers = self._good_headers()
        del headers["Content-Type"]
        response, payload = self._post_json("/api/asks/1/answer", headers, {"answer": "yes"})
        self.assertEqual(response.status, 415)

    def test_json_content_type_with_charset_is_accepted(self):
        headers = self._good_headers()
        headers["Content-Type"] = "application/json; charset=utf-8"
        response, payload = self._post_json("/api/asks/1/answer", headers, {"answer": "yes"})
        self.assertEqual(response.status, 200)

    def test_missing_content_length_is_411(self):
        headers = self._good_headers()
        conn = self._connection()
        conn.putrequest("POST", "/api/asks/1/answer", skip_host=True)
        for name, value in headers.items():
            conn.putheader(name, value)
        conn.endheaders()
        response = conn.getresponse()
        payload = response.read()
        conn.close()
        self.assertEqual(response.status, 411)

    def test_invalid_content_length_is_400(self):
        headers = self._good_headers()
        headers["Content-Length"] = "abc"
        response, payload = self._post("/api/asks/1/answer", headers, b"{}")
        self.assertEqual(response.status, 400)

    def test_oversized_content_length_is_413(self):
        headers = self._good_headers()
        headers["Content-Length"] = "16385"
        response, payload = self._post("/api/asks/1/answer", headers, b"{}")
        self.assertEqual(response.status, 413)

    def test_bad_json_is_400(self):
        response, payload = self._post("/api/asks/1/answer", self._good_headers(), b"{not json")
        self.assertEqual(response.status, 400)

    def test_invalid_utf8_is_400(self):
        response, payload = self._post("/api/asks/1/answer", self._good_headers(), b"\xff\xfe")
        self.assertEqual(response.status, 400)

    def test_non_object_json_is_400(self):
        response, payload = self._post("/api/asks/1/answer", self._good_headers(), b'["yes"]')
        self.assertEqual(response.status, 400)

    def test_missing_key_is_400(self):
        response, payload = self._post_json("/api/asks/1/answer", self._good_headers(), {"text": "yes"})
        self.assertEqual(response.status, 400)

    def test_non_string_answer_is_400(self):
        response, payload = self._post_json("/api/asks/1/answer", self._good_headers(), {"answer": 5})
        self.assertEqual(response.status, 400)

    def test_dismiss_body_must_be_an_object(self):
        response, payload = self._post("/api/asks/1/dismiss", self._good_headers(), b"[]")
        self.assertEqual(response.status, 400)

    def test_non_integer_ids_are_404(self):
        for ask_id in ("abc", "0", "-1", "1.5", "99999999999999999999999"):
            with self.subTest(ask_id=ask_id):
                response, payload = self._post_json(
                    "/api/asks/{}/answer".format(ask_id), self._good_headers(), {"answer": "yes"}
                )
                self.assertEqual(response.status, 404)

    def test_other_post_paths_are_405(self):
        response, payload = self._post_json("/api/board", self._good_headers(), {})
        self.assertEqual(response.status, 405)

    def test_rejections_leave_the_ask_open(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        self._post_json("/api/asks/1/answer", headers, {"answer": "yes"})
        self.assertNotIn("NEEDS YOU · nothing", self._ask_state())

    def test_options_is_405_without_cors_headers(self):
        conn = self._connection()
        conn.request(
            "OPTIONS",
            "/api/asks/1/answer",
            headers={
                "Host": self._host(),
                "Origin": "http://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        response = conn.getresponse()
        response.read()
        conn.close()
        self.assertEqual(response.status, 405)
        names = [name.lower() for name, value in response.getheaders()]
        self.assertFalse([name for name in names if name.startswith("access-control-")])

    def test_post_responses_never_carry_cors_headers(self):
        response, payload = self._answer("yes")
        names = [name.lower() for name, value in response.getheaders()]
        self.assertFalse([name for name in names if name.startswith("access-control-")])


class AnswerTests(WebWriteTestCase):
    def test_answer_succeeds_and_reaches_the_asking_partys_inbox(self):
        response, payload = self._answer("yes go")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/json; charset=utf-8")
        self.assertEqual(json.loads(payload), {"ok": True, "message": "ask #1 answered"})
        self.assertIn("NEEDS YOU · nothing", self._ask_state())
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-1", self.repo_dir)
        self.assertIn('- ask #1 answered by human: "yes go"', out)

    def test_answering_twice_is_422_not_open(self):
        self._answer("yes")
        response, payload = self._answer("again")
        self.assertEqual(response.status, 422)
        self.assertIn("not open", self._error(payload))

    def test_email_in_answer_is_422_and_not_echoed(self):
        response, payload = self._answer("ping jane.doe@example.com")
        self.assertEqual(response.status, 422)
        self.assertIn("email", self._error(payload))
        self.assertNotIn(b"jane.doe", payload)
        self.assertNotIn("NEEDS YOU · nothing", self._ask_state())

    def test_over_long_answer_is_422(self):
        response, payload = self._answer("x" * 1001)
        self.assertEqual(response.status, 422)
        self.assertIn("maximum length", self._error(payload))

    def test_unknown_ask_is_422(self):
        response, payload = self._post_json("/api/asks/42/answer", self._good_headers(), {"answer": "yes"})
        self.assertEqual(response.status, 422)
        self.assertIn("unknown ask", self._error(payload))


class DismissTests(WebWriteTestCase):
    def test_dismiss_succeeds(self):
        response, payload = self._post_json("/api/asks/1/dismiss", self._good_headers(), {})
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(payload), {"ok": True, "message": "ask #1 dismissed"})
        self.assertIn("NEEDS YOU · nothing", self._ask_state())

    def test_dismiss_twice_is_422(self):
        self._post_json("/api/asks/1/dismiss", self._good_headers(), {})
        response, payload = self._post_json("/api/asks/1/dismiss", self._good_headers(), {})
        self.assertEqual(response.status, 422)
        self.assertIn("not open", self._error(payload))


class PageFilesTests(WebWriteTestCase):
    def test_page_files_never_contain_a_token_value(self):
        token = self._token()
        for name in ("index.html", "app.js", "app.css"):
            with self.subTest(name=name):
                response, body = self._get("/" + name, self._host())
                self.assertNotIn(token.encode("utf-8"), body)
