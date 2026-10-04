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

    def _with_notify(self, notify):
        return {"name": "acme", "paths": ["/tmp/*"], "github": {"repos": []}, "notify": notify}

    def test_accepts_notify_command_list(self):
        config.validate_project_config(self._with_notify({"command": ["notify-send", "guild"]}))

    def test_rejects_notify_that_is_not_an_object(self):
        with self.assertRaises(GuildError):
            config.validate_project_config(self._with_notify(["notify-send"]))

    def test_rejects_notify_without_command(self):
        with self.assertRaises(GuildError):
            config.validate_project_config(self._with_notify({}))

    def test_rejects_notify_with_extra_keys(self):
        with self.assertRaises(GuildError):
            config.validate_project_config(self._with_notify({"command": ["x"], "shell": True}))

    def test_rejects_notify_command_string(self):
        with self.assertRaises(GuildError):
            config.validate_project_config(self._with_notify({"command": "notify-send guild"}))

    def test_rejects_empty_notify_command(self):
        with self.assertRaises(GuildError):
            config.validate_project_config(self._with_notify({"command": []}))

    def test_rejects_notify_command_with_empty_or_non_string_item(self):
        for command in (["notify-send", ""], ["notify-send", 3]):
            with self.subTest(command=command):
                with self.assertRaises(GuildError):
                    config.validate_project_config(self._with_notify({"command": command}))

    def _with_lifecycle(self, lifecycle):
        return {"name": "acme", "paths": ["/tmp/*"], "github": {"repos": []}, "lifecycle": lifecycle}

    def _assert_lifecycle_rejected(self, lifecycle, fragment):
        with self.assertRaises(GuildError) as raised:
            config.validate_project_config(self._with_lifecycle(lifecycle))
        self.assertIn(fragment, raised.exception.message)

    def test_accepts_absent_lifecycle(self):
        config.validate_project_config({"name": "acme", "paths": ["/tmp/*"], "github": {"repos": []}})

    def test_accepts_valid_lifecycle(self):
        config.validate_project_config(
            self._with_lifecycle(
                {
                    "on_pr_merged": {"command": ["scripts/cleanup-merged.sh", "--dry-run"], "timeout_minutes": 30},
                    "on_pr_closed": {"command": ["scripts/cleanup-merged.sh"], "timeout_minutes": 5},
                }
            )
        )

    def test_rejects_lifecycle_that_is_not_an_object(self):
        self._assert_lifecycle_rejected(["x"], "'lifecycle' must be an object")

    def test_rejects_unknown_lifecycle_event(self):
        self._assert_lifecycle_rejected(
            {"on_main_red": {"command": ["x"], "timeout_minutes": 1}}, "on_main_red"
        )

    def test_rejects_lifecycle_command_string(self):
        self._assert_lifecycle_rejected(
            {"on_pr_merged": {"command": "scripts/x.sh", "timeout_minutes": 1}},
            "project config 'lifecycle.on_pr_merged.command' must be a non-empty list of strings",
        )

    def test_rejects_bare_list_event_value_with_hint(self):
        self._assert_lifecycle_rejected(
            {"on_pr_merged": ["scripts/x.sh"]},
            "project config 'lifecycle.on_pr_merged' must be an object with 'command' and 'timeout_minutes'",
        )

    def test_rejects_empty_lifecycle_command(self):
        self._assert_lifecycle_rejected(
            {"on_pr_merged": {"command": [], "timeout_minutes": 1}}, "'lifecycle.on_pr_merged.command'"
        )

    def test_rejects_lifecycle_command_with_empty_element(self):
        self._assert_lifecycle_rejected(
            {"on_pr_merged": {"command": ["x", ""], "timeout_minutes": 1}}, "'lifecycle.on_pr_merged.command'"
        )

    def test_rejects_missing_timeout(self):
        self._assert_lifecycle_rejected(
            {"on_pr_closed": {"command": ["x"]}}, "exactly the keys 'command' and 'timeout_minutes'"
        )

    def test_rejects_invalid_timeout_values(self):
        for timeout in (True, 0, -3, "30", 1.5):
            with self.subTest(timeout=timeout):
                self._assert_lifecycle_rejected(
                    {"on_pr_merged": {"command": ["x"], "timeout_minutes": timeout}},
                    "project config 'lifecycle.on_pr_merged.timeout_minutes' must be a positive integer",
                )

    def test_rejects_timeout_above_one_day(self):
        self._assert_lifecycle_rejected(
            {"on_pr_merged": {"command": ["x"], "timeout_minutes": 1441}}, "at most 1440"
        )

    def test_accepts_timeout_of_one_day(self):
        config.validate_project_config(
            self._with_lifecycle({"on_pr_merged": {"command": ["x"], "timeout_minutes": 1440}})
        )

    def test_rejects_project_names_that_traverse_paths(self):
        for name in ("../evil", "a/b", ".hidden", "a..b"):
            with self.subTest(name=name):
                with self.assertRaises(GuildError):
                    config.validate_project_config({"name": name, "paths": ["/tmp/*"], "github": {"repos": []}})

    def test_rejects_extra_lifecycle_event_key(self):
        self._assert_lifecycle_rejected(
            {"on_pr_merged": {"command": ["x"], "timeout_minutes": 1, "shell": True}},
            "exactly the keys 'command' and 'timeout_minutes'",
        )

    def test_rejects_tracker_that_is_not_an_object(self):
        with self.assertRaises(GuildError):
            config.validate_project_config(
                {"name": "acme", "paths": ["/tmp/*"], "github": {"repos": []}, "tracker": "jira"}
            )

    def test_accepts_shared_areas_with_ttl(self):
        config.validate_project_config(
            {
                "name": "acme",
                "paths": ["/tmp/*"],
                "github": {"repos": []},
                "shared_areas": ["config/routes.rb", "db/migrate/*"],
                "shared_area_claim_ttl": "2h",
            }
        )

    def test_rejects_shared_areas_without_ttl(self):
        with self.assertRaises(GuildError):
            config.validate_project_config(
                {
                    "name": "acme",
                    "paths": ["/tmp/*"],
                    "github": {"repos": []},
                    "shared_areas": ["config/routes.rb"],
                }
            )

    def test_rejects_shared_areas_that_is_not_a_list_of_strings(self):
        with self.assertRaises(GuildError):
            config.validate_project_config(
                {
                    "name": "acme",
                    "paths": ["/tmp/*"],
                    "github": {"repos": []},
                    "shared_areas": [1, 2],
                    "shared_area_claim_ttl": "2h",
                }
            )

    def test_accepts_migration_paths(self):
        config.validate_project_config(
            {
                "name": "acme",
                "paths": ["/tmp/*"],
                "github": {"repos": []},
                "migration_paths": ["db/migrate/*.rb"],
            }
        )

    def test_rejects_migration_paths_that_is_not_a_list_of_strings(self):
        with self.assertRaises(GuildError):
            config.validate_project_config(
                {
                    "name": "acme",
                    "paths": ["/tmp/*"],
                    "github": {"repos": []},
                    "migration_paths": "db/migrate/*",
                }
            )

    def test_rejects_shared_area_claim_ttl_with_bad_format(self):
        with self.assertRaises(GuildError):
            config.validate_project_config(
                {
                    "name": "acme",
                    "paths": ["/tmp/*"],
                    "github": {"repos": []},
                    "shared_areas": ["config/routes.rb"],
                    "shared_area_claim_ttl": "soon",
                }
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


class HandoffRetentionConfigTests(unittest.TestCase):
    def _data(self):
        return {"name": "acme", "paths": ["/tmp/*"], "github": {"repos": []}}

    def _with(self, value):
        data = self._data()
        data["handoff_retention_days"] = value
        return data

    def test_absent_is_valid(self):
        config.validate_project_config(self._data())

    def test_positive_integers_up_to_limit_are_accepted(self):
        config.validate_project_config(self._with(30))
        config.validate_project_config(self._with(3650))

    def test_invalid_values_are_rejected(self):
        for value in (0, -1, True, "30", 4000, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(GuildError):
                    config.validate_project_config(self._with(value))


class DispatcherConfigTests(unittest.TestCase):
    def _block(self):
        return {
            "permission_mode": "acceptEdits",
            "max_launches_per_hour": 3,
            "rules": {"ask_answered": "on", "checks_failing": "dry-run"},
        }

    def _data(self, block):
        return {"name": "acme", "paths": ["/tmp/*"], "github": {"repos": []}, "dispatcher": block}

    def _message(self, block):
        with self.assertRaises(GuildError) as raised:
            config.validate_project_config(self._data(block))
        return raised.exception.message

    def test_absent_block_is_valid(self):
        config.validate_project_config({"name": "acme", "paths": ["/tmp/*"], "github": {"repos": []}})

    def test_valid_block_is_accepted(self):
        config.validate_project_config(self._data(self._block()))

    def test_every_allowed_mode_is_accepted(self):
        for mode in ("manual", "acceptEdits", "auto"):
            with self.subTest(mode=mode):
                block = self._block()
                block["permission_mode"] = mode
                config.validate_project_config(self._data(block))

    def test_empty_rules_object_is_accepted(self):
        block = self._block()
        block["rules"] = {}
        config.validate_project_config(self._data(block))

    def test_block_that_is_not_an_object_is_rejected(self):
        self.assertIn("'dispatcher' must be an object", self._message(["x"]))

    def test_each_missing_key_is_rejected(self):
        for key in ("permission_mode", "max_launches_per_hour", "rules"):
            with self.subTest(key=key):
                block = self._block()
                del block[key]
                self.assertIn("exactly the keys", self._message(block))

    def test_extra_key_is_rejected(self):
        block = self._block()
        block["shell"] = True
        self.assertIn("exactly the keys", self._message(block))

    def test_permissive_or_unknown_modes_are_rejected(self):
        for mode in ("bypassPermissions", "dontAsk", "plan", "default", "", 3):
            with self.subTest(mode=mode):
                block = self._block()
                block["permission_mode"] = mode
                self.assertIn("'dispatcher.permission_mode' must be one of", self._message(block))

    def test_max_launches_out_of_range_or_wrong_type_is_rejected(self):
        for value in (0, -1, 21, True, "3", 1.5):
            with self.subTest(value=value):
                block = self._block()
                block["max_launches_per_hour"] = value
                self.assertIn("'dispatcher.max_launches_per_hour' must be an integer", self._message(block))

    def test_max_launches_bounds_are_accepted(self):
        for value in (1, 20):
            with self.subTest(value=value):
                block = self._block()
                block["max_launches_per_hour"] = value
                config.validate_project_config(self._data(block))

    def test_rules_that_is_not_an_object_is_rejected(self):
        block = self._block()
        block["rules"] = ["ask_answered"]
        self.assertIn("'dispatcher.rules' must be an object", self._message(block))

    def test_unknown_rule_is_rejected(self):
        block = self._block()
        block["rules"] = {"merge_everything": "on"}
        self.assertIn("unknown rule 'merge_everything'", self._message(block))

    def test_off_is_rejected_with_hint(self):
        block = self._block()
        block["rules"] = {"ask_answered": "off"}
        message = self._message(block)
        self.assertIn("remove the rule to disable it", message)

    def test_other_rule_values_are_rejected(self):
        block = self._block()
        block["rules"] = {"ask_answered": True}
        self.assertIn("must be 'dry-run' or 'on'", self._message(block))


if __name__ == "__main__":
    unittest.main()
