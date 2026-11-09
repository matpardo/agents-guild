import json

from tests.test_web_write import WebWriteTestCase


class WebPartyGoalTests(WebWriteTestCase):
    def _party(self, name):
        response, body = self._get("/api/board", self._host())
        return next(party for party in json.loads(body)["parties"] if party["name"] == name)

    def _set(self, party, data):
        return self._post_json("/api/parties/{}/goal".format(party), self._good_headers(), data)

    def test_set_both_fields_updates_the_model(self):
        response, payload = self._set("alpha", {"goal": "new goal", "done_when": "new done"})
        self.assertEqual(response.status, 200, payload)
        party = self._party("alpha")
        self.assertEqual((party["goal"], party["done_when"]), ("new goal", "new done"))

    def test_set_one_field_keeps_the_other(self):
        self._set("alpha", {"goal": "g", "done_when": "d"})
        response, payload = self._set("alpha", {"goal": "g2"})
        self.assertEqual(response.status, 200, payload)
        party = self._party("alpha")
        self.assertEqual((party["goal"], party["done_when"]), ("g2", "d"))

    def test_empty_payload_is_422(self):
        response, payload = self._set("alpha", {})
        self.assertEqual(response.status, 422)
        self.assertIn("needs --goal or --done-when", self._error(payload))

    def test_blank_value_is_422(self):
        response, payload = self._set("alpha", {"goal": " "})
        self.assertEqual(response.status, 422)

    def test_non_string_value_is_400(self):
        response, payload = self._set("alpha", {"goal": 3})
        self.assertEqual(response.status, 400)

    def test_unknown_party_is_422(self):
        response, payload = self._set("ghost", {"goal": "g"})
        self.assertEqual(response.status, 422)

    def test_missing_token_is_403(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._post_json("/api/parties/alpha/goal", headers, {"goal": "g"})
        self.assertEqual(response.status, 403)
