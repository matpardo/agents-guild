from guild import context, db, origin, paths, timeutil
from guild.commands import board as board_commands
from guild.commands import memory as memory_commands
from guild.errors import GuildError
from tests.testutil import GuildTestCase


class MemoryTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-2", self.repo_dir)

    def _ctx(self, session_id):
        return context.RunContext(
            db.connect(paths.db_path()),
            session_id,
            self.repo_dir,
            timeutil.utcnow(),
            origin.current_origin(),
            self.sessions_dir,
            self.config_home / "guild" / "projects",
            None,
        )

    def test_add_writes_a_file_with_the_text(self):
        memory_commands.add(self._ctx("sess-1"), "remember this")
        item_path = self.data_home / "guild" / "memory" / "alpha" / "1.md"
        self.assertEqual(item_path.read_text(), "remember this")

    def test_add_from_unbound_session_raises(self):
        with self.assertRaises(GuildError):
            memory_commands.add(self._ctx("sess-unbound"), "x")

    def test_two_adds_get_increasing_seq_and_list_is_newest_first(self):
        memory_commands.add(self._ctx("sess-1"), "first")
        memory_commands.add(self._ctx("sess-1"), "second")
        items = memory_commands.list_items("alpha")
        self.assertEqual([item["seq"] for item in items], [2, 1])
        self.assertEqual([item["text"] for item in items], ["second", "first"])

    def test_add_identical_to_newest_is_a_noop(self):
        memory_commands.add(self._ctx("sess-1"), "same")
        message = memory_commands.add(self._ctx("sess-1"), "same")
        self.assertEqual(message, "skipped: identical to the last memory item")
        self.assertEqual(len(memory_commands.list_items("alpha")), 1)

    def test_add_rejects_text_over_max_length(self):
        with self.assertRaises(GuildError):
            memory_commands.add(self._ctx("sess-1"), "x" * 501)

    def test_add_rejects_embedded_email(self):
        with self.assertRaises(GuildError):
            memory_commands.add(self._ctx("sess-1"), "contact a@b.com")

    def test_add_rejects_secret_pattern(self):
        with self.assertRaises(GuildError):
            memory_commands.add(self._ctx("sess-1"), "token ghp_abcdef1234")

    def test_rm_from_owning_party_succeeds(self):
        memory_commands.add(self._ctx("sess-1"), "x")
        memory_commands.rm(self._ctx("sess-1"), "alpha/1")
        self.assertEqual(memory_commands.list_items("alpha"), [])

    def test_rm_from_different_bound_party_raises(self):
        memory_commands.add(self._ctx("sess-1"), "x")
        with self.assertRaises(GuildError):
            memory_commands.rm(self._ctx("sess-2"), "alpha/1")

    def test_rm_from_unbound_session_removes_any_party(self):
        memory_commands.add(self._ctx("sess-1"), "x")
        memory_commands.rm(self._ctx(None), "alpha/1")
        self.assertEqual(memory_commands.list_items("alpha"), [])

    def test_rm_unknown_item_raises(self):
        with self.assertRaises(GuildError) as raised:
            memory_commands.rm(self._ctx(None), "alpha/1")
        self.assertIn("unknown memory item", str(raised.exception))

    def test_rm_rejects_malformed_party_without_touching_the_filesystem(self):
        with self.assertRaises(GuildError):
            memory_commands.rm(self._ctx(None), "../../etc/1")
        self.assertEqual(list(paths.memory_dir().iterdir()), [])

    def test_rm_rejects_malformed_seq(self):
        with self.assertRaises(GuildError):
            memory_commands.rm(self._ctx(None), "alpha/not-a-number")

    def test_list_rejects_malformed_party(self):
        with self.assertRaises(GuildError):
            memory_commands.list_items("../../etc")

    def test_cli_round_trip(self):
        code, out, err = self.run_cli(["memory", "add", "x"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["memory", "list"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        self.assertIn("alpha/1: x", out)
        code, out, err = self.run_cli(["memory", "rm", "alpha/1"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["memory", "rm", "alpha/1"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)

    def test_board_model_flags_instruction_like_text(self):
        memory_commands.add(self._ctx("sess-1"), "plain text")
        memory_commands.add(self._ctx("sess-2"), "orden del dev: do it")
        ctx = self._ctx(None)
        model = board_commands.board_model(ctx)
        ctx.conn.close()
        by_id = {item["id"]: item for item in model["memory"]}
        self.assertEqual(by_id["alpha/1"]["flagged"], False)
        self.assertEqual(by_id["beta/1"]["flagged"], True)


if __name__ == "__main__":
    import unittest

    unittest.main()
