import json

from tests.test_adventurer import AdventurerTestCase

_PARTY_FLAGS = ["--reason", "test reason", "--goal", "test goal", "--done-when", "test done"]


class SessionTitleTests(AdventurerTestCase):
    def register_session(self, session_id, name, name_source):
        entry = {"pid": 4242, "sessionId": session_id, "name": name, "nameSource": name_source}
        (self.sessions_dir / "4242.json").write_text(json.dumps(entry))

    def prompt(self, session_id):
        code, out, err = self.run_hook("prompt-submit", {"session_id": session_id, "cwd": str(self.repo_dir)})
        self.assertEqual(code, 0, err)
        return out

    def start_party(self, session_id):
        code, out, err = self.cli(["party", "start", "alpha"] + _PARTY_FLAGS, session_id)
        self.assertEqual(code, 0, err)

    def title_output(self, session_id):
        return json.loads(self.prompt(session_id))["hookSpecificOutput"]

    def test_party_session_with_a_derived_name_gets_its_generation_name(self):
        self.register_session("sess-1", "repo-df", "derived")
        self.start_party("sess-1")
        self.cli(["notice", "create", "pipeline down", "--to", "guild", "--ttl", "2h"], None)
        output = self.title_output("sess-1")
        self.assertEqual(output["hookEventName"], "UserPromptSubmit")
        self.assertEqual(output["sessionTitle"], "alpha-g1")
        self.assertIn("pipeline down", output["additionalContext"])

    def test_adventurer_session_gets_its_label(self):
        self.register_session("adv-1", "repo-df", "derived")
        self.start("adv-1", "x", "--task", "demo-epic/T90")
        self.assertEqual(self.title_output("adv-1")["sessionTitle"], "adventurer 1")

    def test_auto_generated_name_is_replaced(self):
        self.register_session("sess-1", "some summary", "auto")
        self.start_party("sess-1")
        self.assertEqual(self.title_output("sess-1")["sessionTitle"], "alpha-g1")

    def test_a_title_set_by_the_hook_follows_the_binding(self):
        self.register_session("sess-1", "adventurer 1", "hook")
        self.start_party("sess-1")
        self.assertEqual(self.title_output("sess-1")["sessionTitle"], "alpha-g1")

    def assert_no_title(self, session_id):
        self.assertNotIn("sessionTitle", self.prompt(session_id))

    def test_a_name_the_human_chose_is_kept(self):
        self.register_session("sess-1", "my-billing-work", "user")
        self.start_party("sess-1")
        self.assert_no_title("sess-1")

    def test_a_collision_name_is_kept(self):
        self.register_session("sess-1", "alpha-g1 2", "collision")
        self.start_party("sess-1")
        self.assert_no_title("sess-1")

    def test_a_session_already_titled_is_left_alone(self):
        self.register_session("sess-1", "alpha-g1", "derived")
        self.start_party("sess-1")
        self.assert_no_title("sess-1")

    def test_a_registry_without_name_source_is_left_alone(self):
        self.write_session(4242, "sess-1", "repo-df")
        self.start_party("sess-1")
        self.assert_no_title("sess-1")

    def test_a_session_missing_from_the_registry_gets_plain_text(self):
        self.start_party("sess-1")
        self.assert_no_title("sess-1")

    def test_an_unbound_session_is_not_titled(self):
        self.register_session("sess-9", "repo-df", "derived")
        self.assert_no_title("sess-9")

    def recorded_leader_names(self):
        return [row["session_name"] for row in self.rows("SELECT session_name FROM leaders ORDER BY generation")]

    def test_party_start_records_the_title_for_a_derived_name(self):
        self.register_session("sess-1", "repo-df", "derived")
        self.start_party("sess-1")
        self.assertEqual(self.recorded_leader_names(), ["alpha-g1"])

    def test_party_start_records_the_name_the_human_chose(self):
        self.register_session("sess-1", "my-billing-work", "user")
        self.start_party("sess-1")
        self.assertEqual(self.recorded_leader_names(), ["my-billing-work"])

    def test_party_resume_records_the_new_generation_title(self):
        self.start_party("sess-1")
        code, out, err = self.cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1")
        self.assertEqual(code, 0, err)
        self.register_session("sess-2", "repo-df", "derived")
        code, out, err = self.cli(["party", "resume", "alpha"], "sess-2")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.recorded_leader_names(), [None, "alpha-g2"])
