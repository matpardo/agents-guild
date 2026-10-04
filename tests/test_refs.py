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

    def test_parses_card_ref(self):
        self.assertEqual(refs.parse_ask_ref("card:PROJ-12"), "card:PROJ-12")

    def test_rejects_blank_card_ref(self):
        with self.assertRaises(GuildError):
            refs.parse_ask_ref("card:")

    def test_rejects_card_ref_with_space_or_slash(self):
        for text in ("card:PROJ 12", "card:PROJ/12"):
            with self.assertRaises(GuildError):
                refs.parse_ask_ref(text)

    def test_rejects_unknown_prefix(self):
        with self.assertRaises(GuildError):
            refs.parse_ask_ref("weird:demo/T01")

    def test_error_lists_the_three_forms(self):
        with self.assertRaises(GuildError) as raised:
            refs.parse_ask_ref("weird:demo/T01")
        message = str(raised.exception)
        self.assertIn("pr:owner/repo#number", message)
        self.assertIn("task:quest/tid", message)
        self.assertIn("card:KEY", message)


class UntilTests(unittest.TestCase):
    def test_parses_merged_condition(self):
        result = refs.parse_until("pr:acme/app#12:merged")
        self.assertEqual(result, {"repo": "acme/app", "number": 12, "state": "merged"})

    def test_rejects_unknown_state(self):
        with self.assertRaises(GuildError):
            refs.parse_until("pr:acme/app#12:archived")


if __name__ == "__main__":
    unittest.main()
