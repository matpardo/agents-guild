import json

from tests.test_web_write import WebWriteTestCase


class WebPartyParkTests(WebWriteTestCase):
    def _party(self, name):
        response, body = self._get("/api/board", self._host())
        return next(party for party in json.loads(body)["parties"] if party["name"] == name)

    def _park(self, party, data):
        return self._post_json("/api/parties/{}/park".format(party), self._good_headers(), data)

    def _unpark(self, party):
        return self._post_json("/api/parties/{}/unpark".format(party), self._good_headers(), {})

    def test_park_sets_the_model_and_status(self):
        response, payload = self._park("alpha", {"reason": "legal answer"})
        self.assertEqual(response.status, 200, payload)
        party = self._party("alpha")
        self.assertEqual(party["parked"], "legal answer")

    def test_unpark_clears_it(self):
        self._park("alpha", {"reason": "legal answer"})
        response, payload = self._unpark("alpha")
        self.assertEqual(response.status, 200, payload)
        self.assertIsNone(self._party("alpha")["parked"])

    def test_unpark_when_not_parked_is_422(self):
        response, payload = self._unpark("alpha")
        self.assertEqual(response.status, 422)
        self.assertIn("is not parked", self._error(payload))

    def test_blank_reason_is_422(self):
        response, payload = self._park("alpha", {"reason": " "})
        self.assertEqual(response.status, 422)

    def test_non_string_reason_is_400(self):
        response, payload = self._park("alpha", {"reason": 3})
        self.assertEqual(response.status, 400)

    def test_unknown_party_is_422(self):
        response, payload = self._park("ghost", {"reason": "x"})
        self.assertEqual(response.status, 422)

    def test_missing_token_is_403(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._post_json("/api/parties/alpha/park", headers, {"reason": "x"})
        self.assertEqual(response.status, 403)
