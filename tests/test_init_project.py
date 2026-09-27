import json

from tests.testutil import GuildTestCase


class InitProjectTests(GuildTestCase):
    def test_registers_valid_config(self):
        config_file = self.write_project_config("acme", ["/tmp/acme/*"], ["acme/app"])
        code, out, err = self.run_cli(["init-project", "acme", "--config", str(config_file)], None, None)
        self.assertEqual(code, 0)
        installed = self.config_home / "guild" / "projects" / "acme.json"
        self.assertTrue(installed.is_file())
        self.assertEqual(json.loads(installed.read_text())["name"], "acme")

    def test_rejects_name_mismatch(self):
        config_file = self.write_project_config("acme", ["/tmp/acme/*"], ["acme/app"])
        code, out, err = self.run_cli(["init-project", "other", "--config", str(config_file)], None, None)
        self.assertEqual(code, 1)
        self.assertIn("does not match", err)

    def test_rejects_missing_file(self):
        code, out, err = self.run_cli(
            ["init-project", "acme", "--config", "/tmp/_does_not_exist.json"], None, None
        )
        self.assertEqual(code, 1)

    def test_rejects_invalid_json(self):
        bad_file = self.root / "bad.json"
        bad_file.write_text("{not json")
        code, out, err = self.run_cli(["init-project", "acme", "--config", str(bad_file)], None, None)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
