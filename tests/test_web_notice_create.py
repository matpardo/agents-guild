import json

from tests.test_web_write import WebWriteTestCase

_CREATE = "/api/notices/create"


class WebNoticeCreateTests(WebWriteTestCase):
    def _notices(self):
        response, body = self._get("/api/board", self._host())
        return json.loads(body)["notices"]

    def _create(self, **overrides):
        data = {"text": "heads up", "to": "project:acme", "ttl": "1h"}
        data.update(overrides)
        return self._post_json(_CREATE, self._good_headers(), data)

    def test_create_adds_a_notice_without_a_party(self):
        response, payload = self._create()
        self.assertEqual(response.status, 200, payload)
        notices = self._notices()
        self.assertEqual([(n["text"], n["scope"]) for n in notices], [("heads up", "project:acme")])

    def test_create_accepts_a_raid_scope(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)
        response, payload = self._create(to="raid:ci")
        self.assertEqual(response.status, 200, payload)

    def test_invalid_input_is_422(self):
        for overrides in ({"text": "  "}, {"to": "project:nope"}, {"to": "bogus"}, {"ttl": "soon"}, {"text": "x" * 5000}):
            response, payload = self._create(**overrides)
            self.assertEqual(response.status, 422, overrides)
        self.assertEqual(self._notices(), [])

    def test_non_string_field_is_400(self):
        response, payload = self._create(ttl=3)
        self.assertEqual(response.status, 400)

    def test_missing_token_and_wrong_origin_are_403(self):
        body = {"text": "x", "to": "project:acme", "ttl": "1h"}
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._post_json(_CREATE, headers, body)
        self.assertEqual(response.status, 403)
        headers = self._good_headers()
        headers["Origin"] = "http://evil.example"
        response, payload = self._post_json(_CREATE, headers, body)
        self.assertEqual(response.status, 403)
        self.assertEqual(self._notices(), [])
