import unittest

from guild import pii
from guild.errors import GuildError


class ValidateFieldTests(unittest.TestCase):
    def test_accepts_clean_text_within_length(self):
        pii.validate_field("all good here", "notice text", pii.NOTICE_TEXT_MAX_LENGTH, [])

    def test_rejects_text_over_max_length(self):
        with self.assertRaises(GuildError):
            pii.validate_field("x" * 10, "notice text", 5, [])

    def test_rejects_email_address(self):
        with self.assertRaises(GuildError):
            pii.validate_field("contact jane.doe@example.com now", "notice text", 500, [])

    def test_error_names_field_but_not_matched_text_for_email(self):
        try:
            pii.validate_field("contact jane.doe@example.com now", "notice text", 500, [])
        except GuildError as error:
            self.assertIn("notice text", error.message)
            self.assertNotIn("jane.doe@example.com", error.message)
        else:
            self.fail("expected GuildError")

    def test_rejects_text_matching_project_pattern(self):
        with self.assertRaises(GuildError):
            pii.validate_field("student Jane Doe missed class", "notice text", 500, [r"Jane Doe"])

    def test_error_names_field_but_not_matched_text_for_project_pattern(self):
        try:
            pii.validate_field("student Jane Doe missed class", "notice text", 500, [r"Jane Doe"])
        except GuildError as error:
            self.assertIn("notice text", error.message)
            self.assertNotIn("Jane Doe", error.message)
        else:
            self.fail("expected GuildError")

    def test_rejects_github_personal_access_token(self):
        with self.assertRaises(GuildError):
            pii.validate_field(
                "the key is ghp_abc123XYZ in the log", "notice text", 500, []
            )

    def test_rejects_github_fine_grained_token(self):
        with self.assertRaises(GuildError):
            pii.validate_field(
                "the key is github_pat_abc123XYZ in the log", "notice text", 500, []
            )

    def test_rejects_openai_style_secret_key(self):
        with self.assertRaises(GuildError):
            pii.validate_field(
                "the key is sk-abc123XYZ in the log", "notice text", 500, []
            )

    def test_rejects_aws_access_key_id(self):
        with self.assertRaises(GuildError):
            pii.validate_field(
                "the key is AKIAABCDEFGHIJKLMNOP in the log", "notice text", 500, []
            )

    def test_rejects_slack_bot_token(self):
        with self.assertRaises(GuildError):
            pii.validate_field(
                "the key is xoxb-abc-123-XYZ in the log", "notice text", 500, []
            )

    def test_rejects_private_key_header(self):
        with self.assertRaises(GuildError):
            pii.validate_field(
                "paste this: -----BEGIN RSA PRIVATE KEY----- then the body",
                "notice text",
                500,
                [],
            )

    def test_error_names_field_but_not_matched_text_for_secret(self):
        try:
            pii.validate_field("the key is ghp_abc123XYZ in the log", "notice text", 500, [])
        except GuildError as error:
            self.assertIn("notice text", error.message)
            self.assertNotIn("ghp_abc123XYZ", error.message)
        else:
            self.fail("expected GuildError")

    def test_accepts_hyphenated_word_containing_secret_substring(self):
        pii.validate_field("run guild pr ask-fix now", "notice text", 500, [])

    def test_accepts_decision_phrase(self):
        pii.validate_field("decisión del dev", "notice text", 500, [])

    def test_length_caps_are_named_constants(self):
        self.assertEqual(pii.NOTICE_TEXT_MAX_LENGTH, 500)
        self.assertEqual(pii.ASK_QUESTION_MAX_LENGTH, 300)
        self.assertEqual(pii.ASK_CONTEXT_MAX_LENGTH, 2000)
        self.assertEqual(pii.ANSWER_MAX_LENGTH, 1000)
        self.assertEqual(pii.HANDOFF_FIELD_MAX_LENGTH, 4000)


if __name__ == "__main__":
    unittest.main()
