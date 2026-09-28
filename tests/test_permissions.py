import stat

from tests.testutil import GuildTestCase


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


class DbPermissionsTests(GuildTestCase):
    def test_db_file_is_owner_only_readable_writable(self):
        self.run_cli(["party", "start", "alpha"], "sess-1", None)
        db_path = self.data_home / "guild" / "guild.db"
        self.assertTrue(db_path.is_file())
        self.assertEqual(_mode(db_path), 0o600)

    def test_db_directory_is_owner_only(self):
        self.run_cli(["party", "start", "alpha"], "sess-1", None)
        db_dir = self.data_home / "guild"
        self.assertEqual(_mode(db_dir), 0o700)

    def test_wal_and_shm_files_are_owner_only_when_present(self):
        self.run_cli(["party", "start", "alpha"], "sess-1", None)
        db_dir = self.data_home / "guild"
        for suffix in ("-wal", "-shm"):
            sibling = db_dir / ("guild.db" + suffix)
            if sibling.exists():
                self.assertEqual(_mode(sibling), 0o600)

    def test_fixes_preexisting_world_readable_db_on_next_run(self):
        self.run_cli(["party", "start", "alpha"], "sess-1", None)
        db_path = self.data_home / "guild" / "guild.db"
        db_dir = self.data_home / "guild"
        db_path.chmod(0o666)
        db_dir.chmod(0o777)
        self.run_cli(["whoami"], "sess-1", None)
        self.assertEqual(_mode(db_path), 0o600)
        self.assertEqual(_mode(db_dir), 0o700)


class DirectoryPermissionsTests(GuildTestCase):
    def test_state_dir_is_owner_only(self):
        self.run_cli(["party", "start", "alpha"], "sess-1", None)
        state_dir = self.state_home / "guild"
        self.assertTrue(state_dir.is_dir())
        self.assertEqual(_mode(state_dir), 0o700)

    def test_handoffs_dir_is_owner_only(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", repo_dir)
        handoffs_dir = self.data_home / "guild" / "handoffs"
        self.assertTrue(handoffs_dir.is_dir())
        self.assertEqual(_mode(handoffs_dir), 0o700)

    def test_projects_config_dir_is_owner_only(self):
        config_file = self.write_project_config("acme", ["/tmp/acme/*"], ["acme/app"])
        self.run_cli(["init-project", "acme", "--config", str(config_file)], None, None)
        projects_dir = self.config_home / "guild" / "projects"
        self.assertTrue(projects_dir.is_dir())
        self.assertEqual(_mode(projects_dir), 0o700)


if __name__ == "__main__":
    import unittest

    unittest.main()
