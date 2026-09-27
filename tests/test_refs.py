import unittest

from guild import refs
from guild.errors import GuildError


class PrRefTests(unittest.TestCase):
    def test_parses_valid_ref(self):
        repo, number = refs.parse_pr_ref("acme/app#12")
        self.assertEqual(repo, "acme/app")
        self.assertEqual(number, 12)

    def test_rejects_missing_number(self):
        with self.assertRaises(GuildError):
            refs.parse_pr_ref("acme/app")


class TaskRefTests(unittest.TestCase):
    def test_parses_valid_ref(self):
        quest, tid = refs.parse_task_ref("demo/T01")
        self.assertEqual(quest, "demo")
        self.assertEqual(tid, "T01")

    def test_rejects_missing_tid(self):
        with self.assertRaises(GuildError):
            refs.parse_task_ref("demo")


class AskRefTests(unittest.TestCase):
    def test_parses_pr_ref(self):
        self.assertEqual(refs.parse_ask_ref("pr:acme/app#12"), "pr:acme/app#12")

    def test_parses_task_ref(self):
        self.assertEqual(refs.parse_ask_ref("task:demo/T01"), "task:demo/T01")

    def test_rejects_unknown_prefix(self):
        with self.assertRaises(GuildError):
            refs.parse_ask_ref("weird:demo/T01")


class UntilTests(unittest.TestCase):
    def test_parses_merged_condition(self):
        result = refs.parse_until("pr:acme/app#12:merged")
        self.assertEqual(result, {"repo": "acme/app", "number": 12, "state": "merged"})

    def test_rejects_unknown_state(self):
        with self.assertRaises(GuildError):
            refs.parse_until("pr:acme/app#12:archived")


if __name__ == "__main__":
    unittest.main()
