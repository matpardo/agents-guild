from guild.adapters import jira_acli
from tests import fake_acli
from tests.testutil import GuildTestCase


def _item(key, status_name, status_category, issue_type):
    return {
        "key": key,
        "fields": {
            "status": {"name": status_name, "statusCategory": {"key": status_category}},
            "issuetype": {"name": issue_type},
        },
    }


class ChildrenOfTests(GuildTestCase):
    def test_returns_parsed_cards_for_valid_epic_key(self):
        self.write_acli_fixture("parent = DEMO-1", [_item("DEMO-2", "In Progress", "indeterminate", "Task")])
        cards, invalid_keys = jira_acli.children_of("DEMO-1")
        self.assertEqual(invalid_keys, [])
        self.assertEqual(
            cards,
            [
                {
                    "key": "DEMO-2",
                    "status": "In Progress",
                    "status_category": "indeterminate",
                    "issue_type": "Task",
                }
            ],
        )

    def test_invalid_epic_key_is_reported_and_never_queried(self):
        cards, invalid_keys = jira_acli.children_of("not-a-key")
        self.assertEqual(cards, [])
        self.assertEqual(invalid_keys, ["not-a-key"])

    def test_nonzero_exit_raises_with_stderr(self):
        self.write_acli_error("parent = DEMO-1", "boom")
        with self.assertRaises(jira_acli.JiraAcliError) as ctx:
            jira_acli.children_of("DEMO-1")
        self.assertIn("boom", str(ctx.exception))

    def test_unparseable_json_raises(self):
        fixture_path = self.acli_fixtures_dir / (fake_acli.fixture_name("parent = DEMO-1") + ".json")
        fixture_path.write_text("not json")
        with self.assertRaises(jira_acli.JiraAcliError):
            jira_acli.children_of("DEMO-1")


class CardsByKeyTests(GuildTestCase):
    def test_returns_parsed_cards_for_valid_keys(self):
        self.write_acli_fixture(
            "key in (DEMO-1,DEMO-2)",
            [
                _item("DEMO-1", "Done", "done", "Story"),
                _item("DEMO-2", "To Do", "new", "Task"),
            ],
        )
        cards, invalid_keys = jira_acli.cards_by_key(["DEMO-1", "DEMO-2"])
        self.assertEqual(invalid_keys, [])
        self.assertEqual({c["key"] for c in cards}, {"DEMO-1", "DEMO-2"})

    def test_invalid_keys_are_filtered_out_and_reported(self):
        self.write_acli_fixture("key in (DEMO-1)", [_item("DEMO-1", "Done", "done", "Story")])
        cards, invalid_keys = jira_acli.cards_by_key(["DEMO-1", "not-a-key"])
        self.assertEqual(invalid_keys, ["not-a-key"])
        self.assertEqual([c["key"] for c in cards], ["DEMO-1"])

    def test_more_than_fifty_keys_are_queried_in_two_chunks(self):
        keys = ["DEMO-{}".format(i) for i in range(1, 52)]
        first_chunk = keys[:50]
        second_chunk = keys[50:]
        self.write_acli_fixture(
            "key in ({})".format(",".join(first_chunk)),
            [_item(key, "To Do", "new", "Task") for key in first_chunk],
        )
        self.write_acli_fixture(
            "key in ({})".format(",".join(second_chunk)),
            [_item(key, "To Do", "new", "Task") for key in second_chunk],
        )
        cards, invalid_keys = jira_acli.cards_by_key(keys)
        self.assertEqual(invalid_keys, [])
        self.assertEqual({c["key"] for c in cards}, set(keys))

    def test_empty_keys_gives_empty_result_without_querying(self):
        cards, invalid_keys = jira_acli.cards_by_key([])
        self.assertEqual(cards, [])
        self.assertEqual(invalid_keys, [])


if __name__ == "__main__":
    import unittest

    unittest.main()
