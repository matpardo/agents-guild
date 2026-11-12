import json
import os
from unittest import mock

from tests.test_web_write import WebWriteTestCase


class FakeTmux:
    def __init__(self):
        self.windows = []

    def installed(self):
        return True

    def run(self, args):
        if args[0] == "has-session":
            return 1, ""
        if args[0] in ("new-session", "new-window"):
            self.windows.append(args[args.index("-n") + 1])
            return 0, "@{}\n".format(len(self.windows))
        return 0, ""


class WebReviveTests(WebWriteTestCase):
    def setUp(self):
        super().setUp()
        self.tmux = FakeTmux()
        patcher = mock.patch("guild.tmux_windows.Tmux", return_value=self.tmux)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.run_cli(
            ["quest", "add", "chore", "--open", "--no-epic", "--title", "chore", "--tasks", "T01", "--titles", "one"],
            None,
            self.repo_dir,
        )
        self.run_cli(
            ["adventurer", "start", "fix typo", "--task", "chore/T01", "--reason", "test reason"],
            "adv-1",
            self.repo_dir,
        )
        directory = self.claude_projects_dir / "-x"
        directory.mkdir(parents=True)
        for session_id in ("sess-1", "adv-1"):
            (directory / "{}.jsonl".format(session_id)).write_text(json.dumps({"cwd": str(self.repo_dir)}) + "\n")

    def _post_revive(self, path, headers=None):
        return self._post_json(path, headers or self._good_headers(), {})

    def test_revive_all_launches_party_and_adventurer(self):
        response, payload = self._post_revive("/api/revive")
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(sorted(self.tmux.windows), ["adventurer-1", "alpha"])
        self.assertIn("launched alpha", json.loads(payload)["message"])

    def test_revive_party_launches_only_that_party(self):
        response, payload = self._post_revive("/api/parties/alpha/revive")
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(self.tmux.windows, ["alpha"])

    def test_revive_adventurer_launches_only_that_adventurer(self):
        response, payload = self._post_revive("/api/adventurers/1/revive")
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(self.tmux.windows, ["adventurer-1"])

    def test_live_leader_is_reported_as_skipped(self):
        self.write_session(os.getpid(), "sess-1", "alpha-g1")
        response, payload = self._post_revive("/api/parties/alpha/revive")
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(self.tmux.windows, [])
        self.assertIn("skipped alpha: leader session is live", json.loads(payload)["message"])

    def test_unknown_party_and_adventurer_are_422(self):
        self.assertEqual(self._post_revive("/api/parties/ghost/revive")[0].status, 422)
        self.assertEqual(self._post_revive("/api/adventurers/9/revive")[0].status, 422)

    def test_bad_adventurer_id_is_404(self):
        self.assertEqual(self._post_revive("/api/adventurers/abc/revive")[0].status, 404)

    def test_missing_token_is_403_on_every_route(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        for path in ("/api/revive", "/api/parties/alpha/revive", "/api/adventurers/1/revive"):
            self.assertEqual(self._post_revive(path, headers)[0].status, 403, path)
        self.assertEqual(self.tmux.windows, [])


if __name__ == "__main__":
    import unittest

    unittest.main()
