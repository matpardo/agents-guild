import unittest
from pathlib import Path

from guild import names
from guild.errors import GuildError


class ValidateNameTests(unittest.TestCase):
    def test_accepts_simple_name(self):
        self.assertEqual(names.validate_name("alpha", "party name"), "alpha")

    def test_accepts_dots_dashes_and_underscores(self):
        names.validate_name("alpha-2.beta_3", "party name")

    def test_rejects_empty_string(self):
        with self.assertRaises(GuildError):
            names.validate_name("", "party name")

    def test_rejects_leading_dot(self):
        with self.assertRaises(GuildError):
            names.validate_name(".hidden", "party name")

    def test_rejects_path_separator(self):
        with self.assertRaises(GuildError):
            names.validate_name("a/b", "party name")

    def test_rejects_parent_traversal(self):
        with self.assertRaises(GuildError):
            names.validate_name("../../tmp/x", "party name")

    def test_rejects_dotdot_anywhere_in_name(self):
        with self.assertRaises(GuildError):
            names.validate_name("foo..bar", "party name")

    def test_error_names_the_field(self):
        try:
            names.validate_name("../evil", "quest slug")
        except GuildError as error:
            self.assertIn("quest slug", error.message)
        else:
            self.fail("expected GuildError")


class EnsureWithinTests(unittest.TestCase):
    def test_path_inside_base_is_returned_resolved(self):
        base = Path("/tmp/guild-names-test-base")
        candidate = base / "child.md"
        self.assertEqual(names.ensure_within(candidate, base), candidate.resolve())

    def test_path_escaping_base_raises(self):
        base = Path("/tmp/guild-names-test-base")
        escaping = base / ".." / ".." / "etc" / "passwd"
        with self.assertRaises(GuildError):
            names.ensure_within(escaping, base)


if __name__ == "__main__":
    unittest.main()
