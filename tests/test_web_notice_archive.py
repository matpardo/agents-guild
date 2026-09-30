import json

from tests.test_web_write import WebWriteTestCase

_ACTIONS = ("archive", "unarchive")


class NoticeWebTestCase(WebWriteTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["notice", "create", "pipeline down", "--to", "guild", "--ttl", "5h"], None, None)

    def _notice_post(self, action, headers, body):
        return self._post("/api/notices/1/{}".format(action), headers, body)

    def _notice_action(self, action):
        return self._post_json("/api/notices/1/{}".format(action), self._good_headers(), {})

    def _archived_ids(self):
        response, body = self._get("/api/archived-notices", self._host())
        return [notice["id"] for notice in json.loads(body)["notices"]]

    def _visible_ids(self):
        response, body = self._get("/api/board", self._host())
        return [notice["id"] for notice in json.loads(body)["notices"]]


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
                conn.request(method, "/api/notices/1/archive", headers={"Host": self._host()})
                response = conn.getresponse()
                response.read()
                conn.close()
                self.assertEqual(response.status, 405)

    def test_responses_never_carry_cors_headers(self):
        response, payload = self._notice_action("archive")
        names = [name.lower() for name, value in response.getheaders()]
        self.assertFalse([name for name in names if name.startswith("access-control-")])

    def test_rejections_leave_the_notice_unarchived(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        self._notice_post("archive", headers, b"{}")
        self.assertEqual(self._visible_ids(), [1])
        self.assertEqual(self._archived_ids(), [])


class NoticeActionTests(NoticeWebTestCase):
    def test_archive_succeeds_and_moves_the_notice_between_lists(self):
        response, payload = self._notice_action("archive")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/json; charset=utf-8")
        self.assertEqual(json.loads(payload), {"ok": True, "message": "notice #1 archived"})
        self.assertEqual(self._visible_ids(), [])
        self.assertEqual(self._archived_ids(), [1])
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertEqual(out, "1 archived (guild notices --archived)\n")

    def test_unarchive_succeeds(self):
        self._notice_action("archive")
        response, payload = self._notice_action("unarchive")
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(payload), {"ok": True, "message": "notice #1 unarchived"})
        self.assertEqual(self._visible_ids(), [1])
        self.assertEqual(self._archived_ids(), [])

    def test_unknown_notice_is_422(self):
        for action in _ACTIONS:
            with self.subTest(action=action):
                response, payload = self._post_json(
                    "/api/notices/42/{}".format(action), self._good_headers(), {}
                )
                self.assertEqual(response.status, 422)
                self.assertIn("unknown notice", self._error(payload))

    def test_archiving_twice_is_422(self):
        self._notice_action("archive")
        response, payload = self._notice_action("archive")
        self.assertEqual(response.status, 422)
        self.assertIn("already archived", self._error(payload))

    def test_unarchiving_a_visible_notice_is_422(self):
        response, payload = self._notice_action("unarchive")
        self.assertEqual(response.status, 422)
        self.assertIn("not archived", self._error(payload))

    def test_closed_notice_is_422(self):
        self.run_cli(["notice", "close", "1"], None, None)
        response, payload = self._notice_action("archive")
        self.assertEqual(response.status, 422)
        self.assertIn("not active", self._error(payload))

    def test_archiving_over_the_web_does_not_change_inbox_delivery(self):
        self._notice_action("archive")
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.assertIn("pipeline down", out)


class ArchivedPageTests(NoticeWebTestCase):
    def test_archived_page_is_served_with_security_headers(self):
        response, body = self._get("/archived", self._host())
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/html; charset=utf-8")
        self.assertIn(b"<!DOCTYPE html>", body)
        self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.getheader("Referrer-Policy"), "no-referrer")
        self.assertIn("default-src 'self'", response.getheader("Content-Security-Policy"))
        self.assertIn("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))

    def test_archived_script_is_served_as_javascript(self):
        response, body = self._get("/archived.js", self._host())
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/javascript; charset=utf-8")
        self.assertTrue(body)

    def test_archived_page_rejects_a_bad_host(self):
        response, body = self._get("/archived", "evil.example")
        self.assertEqual(response.status, 421)

    def test_archived_api_lists_archived_notices_uncached(self):
        self._notice_action("archive")
        response, body = self._get("/api/archived-notices", self._host())
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertIn("default-src 'self'", response.getheader("Content-Security-Policy"))
        notice = json.loads(body)["notices"][0]
        self.assertEqual(notice["text"], "pipeline down")
        self.assertEqual(notice["time_left"], "4h left")

    def test_archived_api_rejects_a_bad_host(self):
        response, body = self._get("/api/archived-notices", "evil.example")
        self.assertEqual(response.status, 421)

    def test_pages_never_contain_a_token_value(self):
        token = self._token()
        for path in ("/archived", "/archived.js", "/api/archived-notices"):
            with self.subTest(path=path):
                response, body = self._get(path, self._host())
                self.assertNotIn(token.encode("utf-8"), body)


if __name__ == "__main__":
    import unittest

    unittest.main()
