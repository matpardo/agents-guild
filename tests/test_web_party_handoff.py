import json
import os
import sqlite3

from tests.test_web_write import WebWriteTestCase


class WebPartyHandoffTests(WebWriteTestCase):
    def _board(self):
        response, body = self._get("/api/board", self._host())
        return json.loads(body)

    def _party(self, name):
        return next(party for party in self._board()["parties"] if party["name"] == name)

    def _hand_off(self, party):
        return self._post_json("/api/parties/{}/hand-off".format(party), self._good_headers(), {})

    def test_hand_off_succeeds_when_no_live_leader(self):
        response, payload = self._hand_off("alpha")
        self.assertEqual(response.status, 200, payload)
        party = self._party("alpha")
        self.assertEqual(party["state"], "awaiting-leader")
        self.assertFalse(party["has_live_leader"])

    def test_hand_off_records_an_auto_event(self):
        self._hand_off("alpha")
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT payload FROM events WHERE kind = 'party.handed_off' ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        conn.close()
        self.assertTrue(json.loads(row["payload"])["auto"])

    def test_hand_off_with_a_live_leader_is_422(self):
        self.write_session(os.getpid(), "sess-1", "alpha-g1")
        response, payload = self._hand_off("alpha")
        self.assertEqual(response.status, 422)
        self.assertIn("has a live leader", self._error(payload))

    def test_unknown_party_is_422(self):
        response, payload = self._hand_off("ghost")
        self.assertEqual(response.status, 422)
        self.assertIn("unknown party", self._error(payload))

    def test_missing_token_is_403(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        response, payload = self._post_json("/api/parties/alpha/hand-off", headers, {})
        self.assertEqual(response.status, 403)

    def test_wrong_origin_is_403(self):
        headers = self._good_headers()
        headers["Origin"] = "http://evil.example"
        response, payload = self._post_json("/api/parties/alpha/hand-off", headers, {})
        self.assertEqual(response.status, 403)


if __name__ == "__main__":
    import unittest

    unittest.main()
