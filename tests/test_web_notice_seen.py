import json

from tests.test_web_write import WebWriteTestCase

_ACTIONS = ("seen", "unseen")


class NoticeWebTestCase(WebWriteTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["notice", "create", "pipeline down", "--to", "guild", "--ttl", "5h"], None, None)

    def _notice_post(self, action, headers, body):
        return self._post("/api/notices/1/{}".format(action), headers, body)

    def _notice_action(self, action):
        return self._post_json("/api/notices/1/{}".format(action), self._good_headers(), {})

    def _seen_flags(self):
        response, body = self._get("/api/board", self._host())
        return {notice["id"]: notice["seen"] for notice in json.loads(body)["notices"]}

    def _seen_all(self):
        return self._post_json("/api/notices/seen-all", self._good_headers(), {})


class NoticeRejectionTests(NoticeWebTestCase):
    def _each_action(self, check):
        for action in _ACTIONS:
            with self.subTest(action=action):
                check(action)

    def test_bad_host_is_421(self):
        def check(action):
            headers = self._good_headers()
            headers["Host"] = "evil.example"
            response, payload = self._notice_post(action, headers, b"{}")
            self.assertEqual(response.status, 421)

        self._each_action(check)

    def test_missing_or_wrong_origin_is_403(self):
        def check(action):
            for origin in (None, "http://evil.example", "null"):
                headers = self._good_headers()
                if origin is None:
                    del headers["Origin"]
                else:
                    headers["Origin"] = origin
                response, payload = self._notice_post(action, headers, b"{}")
                self.assertEqual(response.status, 403)
                self.assertIn("error", json.loads(payload))

        self._each_action(check)

    def test_missing_or_wrong_token_is_403(self):
        def check(action):
            missing = self._good_headers()
            del missing["X-Guild-Token"]
            wrong = self._good_headers()
            wrong["X-Guild-Token"] = "wrong"
            for headers in (missing, wrong):
                response, payload = self._notice_post(action, headers, b"{}")
                self.assertEqual(response.status, 403)

        self._each_action(check)

    def test_wrong_content_type_is_415(self):
        def check(action):
            headers = self._good_headers()
            headers["Content-Type"] = "text/plain"
            response, payload = self._notice_post(action, headers, b"{}")
            self.assertEqual(response.status, 415)

        self._each_action(check)

    def test_missing_content_length_is_411(self):
        def check(action):
            conn = self._connection()
            conn.putrequest("POST", "/api/notices/1/{}".format(action), skip_host=True)
            for name, value in self._good_headers().items():
                conn.putheader(name, value)
            conn.endheaders()
            response = conn.getresponse()
            response.read()
            conn.close()
            self.assertEqual(response.status, 411)

        self._each_action(check)

    def test_invalid_and_oversized_content_length(self):
        def check(action):
            for length, status in (("abc", 400), ("16385", 413)):
                headers = self._good_headers()
                headers["Content-Length"] = length
                response, payload = self._notice_post(action, headers, b"{}")
                self.assertEqual(response.status, status)

        self._each_action(check)

    def test_malformed_bodies_are_400(self):
        def check(action):
            for body in (b"{not json", b"\xff\xfe", b"[]"):
                response, payload = self._notice_post(action, self._good_headers(), body)
                self.assertEqual(response.status, 400)

        self._each_action(check)

    def test_non_integer_ids_are_404(self):
        def check(action):
            for notice_id in ("abc", "0", "-1", "1.5", "99999999999999999999999"):
                response, payload = self._post_json(
                    "/api/notices/{}/{}".format(notice_id, action), self._good_headers(), {}
                )
                self.assertEqual(response.status, 404)

        self._each_action(check)

    def test_unknown_action_is_405(self):
        response, payload = self._post_json("/api/notices/1/close", self._good_headers(), {})
        self.assertEqual(response.status, 405)

    def test_options_is_405_without_cors_headers(self):
        def check(action):
            conn = self._connection()
            conn.request(
                "OPTIONS",
                "/api/notices/1/{}".format(action),
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

        self._each_action(check)

    def test_put_and_delete_are_405(self):
        for method in ("PUT", "DELETE"):
            with self.subTest(method=method):
                conn = self._connection()
                conn.request(method, "/api/notices/1/seen", headers={"Host": self._host()})
                response = conn.getresponse()
                response.read()
                conn.close()
                self.assertEqual(response.status, 405)

    def test_responses_never_carry_cors_headers(self):
        response, payload = self._notice_action("seen")
        names = [name.lower() for name, value in response.getheaders()]
        self.assertFalse([name for name in names if name.startswith("access-control-")])

    def test_rejections_leave_the_notice_unseen(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        self._notice_post("seen", headers, b"{}")
        self.assertEqual(self._seen_flags(), {1: False})


class SeenAllRejectionTests(NoticeWebTestCase):
    def _post_all(self, headers, body):
        return self._post("/api/notices/seen-all", headers, body)

    def test_bad_host_is_421(self):
        headers = self._good_headers()
        headers["Host"] = "evil.example"
        response, payload = self._post_all(headers, b"{}")
        self.assertEqual(response.status, 421)

    def test_missing_or_wrong_origin_is_403(self):
        for origin in (None, "http://evil.example", "null"):
            with self.subTest(origin=origin):
                headers = self._good_headers()
                if origin is None:
                    del headers["Origin"]
                else:
                    headers["Origin"] = origin
                response, payload = self._post_all(headers, b"{}")
                self.assertEqual(response.status, 403)

    def test_missing_or_wrong_token_is_403(self):
        missing = self._good_headers()
        del missing["X-Guild-Token"]
        wrong = self._good_headers()
        wrong["X-Guild-Token"] = "wrong"
        for headers in (missing, wrong):
            response, payload = self._post_all(headers, b"{}")
            self.assertEqual(response.status, 403)
        self.assertEqual(self._seen_flags(), {1: False})

    def test_wrong_content_type_is_415(self):
        headers = self._good_headers()
        headers["Content-Type"] = "text/plain"
        response, payload = self._post_all(headers, b"{}")
        self.assertEqual(response.status, 415)

    def test_missing_content_length_is_411(self):
        conn = self._connection()
        conn.putrequest("POST", "/api/notices/seen-all", skip_host=True)
        for name, value in self._good_headers().items():
            conn.putheader(name, value)
        conn.endheaders()
        response = conn.getresponse()
        response.read()
        conn.close()
        self.assertEqual(response.status, 411)

    def test_invalid_and_oversized_content_length(self):
        for length, status in (("abc", 400), ("16385", 413)):
            headers = self._good_headers()
            headers["Content-Length"] = length
            response, payload = self._post_all(headers, b"{}")
            self.assertEqual(response.status, status)

    def test_malformed_bodies_are_400(self):
        for body in (b"{not json", b"\xff\xfe", b"[]"):
            response, payload = self._post_all(self._good_headers(), body)
            self.assertEqual(response.status, 400)

    def test_options_put_and_delete_are_405_without_cors_headers(self):
        for method in ("OPTIONS", "PUT", "DELETE"):
            with self.subTest(method=method):
                conn = self._connection()
                conn.request(
                    method,
                    "/api/notices/seen-all",
                    headers={"Host": self._host(), "Origin": "http://evil.example"},
                )
                response = conn.getresponse()
                response.read()
                conn.close()
                self.assertEqual(response.status, 405)
                names = [name.lower() for name, value in response.getheaders()]
                self.assertFalse([name for name in names if name.startswith("access-control-")])

    def test_response_carries_no_cors_headers(self):
        response, payload = self._seen_all()
        names = [name.lower() for name, value in response.getheaders()]
        self.assertFalse([name for name in names if name.startswith("access-control-")])


class NoticeActionTests(NoticeWebTestCase):
    def test_seen_succeeds_and_flips_the_flag(self):
        response, payload = self._notice_action("seen")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/json; charset=utf-8")
        self.assertEqual(json.loads(payload), {"ok": True, "message": "notice #1 seen"})
        self.assertEqual(self._seen_flags(), {1: True})
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertTrue(out.startswith("#1 [human] pipeline down (guild, "), out)

    def test_unseen_succeeds(self):
        self._notice_action("seen")
        response, payload = self._notice_action("unseen")
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(payload), {"ok": True, "message": "notice #1 unseen"})
        self.assertEqual(self._seen_flags(), {1: False})

    def test_seen_all_marks_every_notice(self):
        self.run_cli(["notice", "create", "ci flaky", "--to", "guild", "--ttl", "2h"], None, None)
        response, payload = self._seen_all()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(payload), {"ok": True, "message": "2 notices marked seen"})
        self.assertEqual(self._seen_flags(), {1: True, 2: True})

    def test_seen_all_with_nothing_new_is_200(self):
        self._notice_action("seen")
        response, payload = self._seen_all()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(payload)["message"], "0 notices marked seen")

    def test_unknown_notice_is_422(self):
        for action in _ACTIONS:
            with self.subTest(action=action):
                response, payload = self._post_json("/api/notices/42/{}".format(action), self._good_headers(), {})
                self.assertEqual(response.status, 422)
                self.assertIn("unknown notice", self._error(payload))

    def test_seen_twice_is_422(self):
        self._notice_action("seen")
        response, payload = self._notice_action("seen")
        self.assertEqual(response.status, 422)
        self.assertIn("already seen", self._error(payload))

    def test_unseen_on_an_unseen_notice_is_422(self):
        response, payload = self._notice_action("unseen")
        self.assertEqual(response.status, 422)
        self.assertIn("not seen", self._error(payload))

    def test_closed_notice_is_422(self):
        self.run_cli(["notice", "close", "1"], None, None)
        response, payload = self._notice_action("seen")
        self.assertEqual(response.status, 422)
        self.assertIn("not active", self._error(payload))

    def test_marking_over_the_web_does_not_change_inbox_delivery(self):
        self._notice_action("seen")
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-2", self.repo_dir)
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.assertIn("pipeline down", out)

    def test_static_pages_never_contain_the_token(self):
        token = self._token()
        for path in ("/", "/app.js", "/api/board"):
            with self.subTest(path=path):
                response, body = self._get(path, self._host())
                self.assertNotIn(token.encode("utf-8"), body)


if __name__ == "__main__":
    import unittest

    unittest.main()
