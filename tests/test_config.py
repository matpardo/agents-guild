import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from guild import config
from guild.errors import GuildError


class ValidateProjectConfigTests(unittest.TestCase):
    def test_accepts_minimal_valid_config(self):
        config.validate_project_config(
            {"name": "acme", "paths": ["/tmp/acme/*"], "github": {"repos": ["acme/app"]}}
        )

    def test_rejects_missing_name(self):
        with self.assertRaises(GuildError):
            config.validate_project_config({"paths": ["/tmp/*"], "github": {"repos": []}})

    def test_rejects_missing_paths(self):
        with self.assertRaises(GuildError):
            config.validate_project_config({"name": "acme", "github": {"repos": []}})

    def test_rejects_missing_github_repos(self):
        with self.assertRaises(GuildError):
            config.validate_project_config({"name": "acme", "paths": ["/tmp/*"]})

    def test_allows_unknown_keys(self):
        config.validate_project_config(
            {
                "name": "acme",
                "paths": ["/tmp/*"],
                "github": {"repos": []},
                "jira": {"project": "DEMO"},
            }
        )

    def test_accepts_tracker_without_browse_url(self):
        config.validate_project_config(
            {"name": "acme", "paths": ["/tmp/*"], "github": {"repos": []}, "tracker": {"kind": "jira-acli"}}
        )

    def test_accepts_tracker_browse_url_starting_with_https(self):
        config.validate_project_config(
            {
                "name": "acme",
                "paths": ["/tmp/*"],
                "github": {"repos": []},
                "tracker": {"browse_url": "https://tracker.example/browse/"},
            }
        )

    def test_rejects_tracker_browse_url_without_https(self):
        with self.assertRaises(GuildError):
            config.validate_project_config(
                {
                    "name": "acme",
                    "paths": ["/tmp/*"],
                    "github": {"repos": []},
                    "tracker": {"browse_url": "http://tracker.example/browse/"},
                }
            )

    def test_rejects_tracker_that_is_not_an_object(self):
        with self.assertRaises(GuildError):
            config.validate_project_config(
                {"name": "acme", "paths": ["/tmp/*"], "github": {"repos": []}, "tracker": "jira"}
            )


class LoadProjectUnknownProjectTests(unittest.TestCase):
    def test_unknown_project_lists_known_project_names(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "acme.json").write_text(
                json.dumps({"name": "acme", "paths": ["/tmp/*"], "github": {"repos": []}})
            )
            (directory / "zeta.json").write_text(
                json.dumps({"name": "zeta", "paths": ["/tmp/*"], "github": {"repos": []}})
            )
            with self.assertRaises(GuildError) as raised:
                config.load_project(directory, "ghost")
            self.assertEqual(
                raised.exception.message,
                "unknown project 'ghost': known projects are acme, zeta",
            )

    def test_unknown_project_with_no_projects_registered(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with self.assertRaises(GuildError) as raised:
                config.load_project(directory, "ghost")
            self.assertEqual(
                raised.exception.message, "unknown project 'ghost': known projects are none"
            )


class RequireProjectUnknownProjectTests(unittest.TestCase):
    def test_no_match_lists_known_project_names(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "acme.json").write_text(
                json.dumps({"name": "acme", "paths": ["/tmp/_fixture/acme/*"], "github": {"repos": []}})
            )
            with self.assertRaises(GuildError) as raised:
                config.require_project(Path("/tmp/_fixture/other"), directory)
            self.assertIn("known projects are acme", raised.exception.message)


class ResolveProjectTests(unittest.TestCase):
    def test_matches_direct_child_of_glob(self):
        projects = [{"name": "acme", "paths": ["/tmp/_fixture/acme/*"]}]
        result = config.resolve_project(Path("/tmp/_fixture/acme/app"), projects)
        self.assertEqual(result, "acme")

    def test_matches_deep_descendant_via_ancestor(self):
        projects = [{"name": "acme", "paths": ["/tmp/_fixture/acme/app"]}]
        result = config.resolve_project(Path("/tmp/_fixture/acme/app/sub/dir"), projects)
        self.assertEqual(result, "acme")

    def test_returns_none_when_no_match(self):
        projects = [{"name": "acme", "paths": ["/tmp/_fixture/acme/*"]}]
        result = config.resolve_project(Path("/tmp/_fixture/other/app"), projects)
        self.assertIsNone(result)

    def test_first_match_wins_in_list_order(self):
        projects = [
            {"name": "first", "paths": ["/tmp/_fixture/acme/*"]},
            {"name": "second", "paths": ["/tmp/_fixture/acme/*"]},
        ]
        result = config.resolve_project(Path("/tmp/_fixture/acme/app"), projects)
        self.assertEqual(result, "first")


class LoadAllProjectsTests(unittest.TestCase):
    def test_loads_sorted_by_filename(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "zeta.json").write_text(
                json.dumps({"name": "zeta", "paths": ["/tmp/*"], "github": {"repos": []}})
            )
            (directory / "alpha.json").write_text(
                json.dumps({"name": "alpha", "paths": ["/tmp/*"], "github": {"repos": []}})
            )
            projects = config.load_all_projects(directory)
            self.assertEqual([p["name"] for p in projects], ["alpha", "zeta"])

    def test_returns_empty_list_for_missing_dir(self):
        self.assertEqual(config.load_all_projects(Path("/tmp/_does_not_exist_guild")), [])


if __name__ == "__main__":
    unittest.main()
