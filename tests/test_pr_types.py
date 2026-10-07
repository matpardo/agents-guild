import unittest

from guild import pr_types


class FromBranchTests(unittest.TestCase):
    def test_every_canonical_type_maps_to_itself(self):
        for name in pr_types.TYPES:
            with self.subTest(name=name):
                self.assertEqual(pr_types.from_branch("{}/thing".format(name)), name)

    def test_aliases_map_to_their_canonical_type(self):
        cases = {
            "feature/x": "feat",
            "bugfix/x": "fix",
            "bug/x": "fix",
            "doc/x": "docs",
            "tests/x": "test",
        }
        for branch, expected in cases.items():
            with self.subTest(branch=branch):
                self.assertEqual(pr_types.from_branch(branch), expected)

    def test_hotfix_is_its_own_type(self):
        self.assertEqual(pr_types.from_branch("hotfix/main-red"), "hotfix")

    def test_flaky_branch_is_only_a_fix(self):
        self.assertEqual(pr_types.from_branch("fix/flaky-timeouts"), "fix")

    def test_prefix_case_is_ignored(self):
        self.assertEqual(pr_types.from_branch("FEAT/Thing"), "feat")

    def test_unknown_prefix_has_no_type(self):
        self.assertIsNone(pr_types.from_branch("wip/x"))

    def test_branch_without_separator_has_no_type(self):
        self.assertIsNone(pr_types.from_branch("feat-x"))

    def test_missing_branch_has_no_type(self):
        self.assertIsNone(pr_types.from_branch(None))
        self.assertIsNone(pr_types.from_branch(""))


class ResolveTests(unittest.TestCase):
    def test_explicit_wins_over_the_branch(self):
        self.assertEqual(pr_types.resolve("hotfix", "feat/x"), "hotfix")

    def test_explicit_wins_over_an_unknown_prefix(self):
        self.assertEqual(pr_types.resolve("chore", "wip/x"), "chore")

    def test_branch_is_used_when_nothing_is_explicit(self):
        self.assertEqual(pr_types.resolve(None, "fix/x"), "fix")

    def test_nothing_known_resolves_to_nothing(self):
        self.assertIsNone(pr_types.resolve(None, "wip/x"))
