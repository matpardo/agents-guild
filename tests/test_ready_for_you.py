import re

from guild import context, db, paths, timeutil
from guild.commands import board as board_commands
from tests.test_review_md import ReviewMdTestCase

_BOARD_REF_RE = re.compile(r"^  (\S+#\d+) ", re.MULTILINE)
_REVIEW_REF_RE = re.compile(r"^- \[ \] (\S+)", re.MULTILINE)


class ReadyForYouTestCase(ReviewMdTestCase):
    def model(self):
        conn = db.connect(paths.db_path())
        ctx = context.RunContext(
            conn,
            None,
            None,
            timeutil.utcnow(),
            None,
            paths.claude_sessions_dir(),
            paths.projects_config_dir(),
            paths.state_dir(),
        )
        try:
            return board_commands.board_model(ctx)
        finally:
            conn.close()

    def board(self, argv):
        code, out, err = self.run_cli(["board"] + argv, "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        return out

    def section(self, argv):
        out = self.board(argv)
        start = out.index("READY FOR YOU")
        end = out.find("\n\n", start)
        return out[start:] if end == -1 else out[start:end]

    def section_refs(self, argv):
        return _BOARD_REF_RE.findall(self.section(argv))

    def web_refs(self):
        return [item["ref"] for item in self.model()["ready_for_you"]]

    def track_two_parties(self):
        self.track_ready("sess-1", 1, "qa/T01", title="First")
        self.track_ready("sess-1", 2, "qa/T02", title="Second")
        self.track_ready("sess-2", 3, "qb/T01", title="Third")
        self.sync_gh("sess-1")
        self.run_cli(["merge-queue", "pin", "acme/app#2", "--before", "acme/app#1"], "sess-1", self.repo_dir)


class ModelTests(ReadyForYouTestCase):
    def test_empty_when_nothing_is_ready(self):
        self.assertEqual(self.model()["ready_for_you"], [])

    def test_items_follow_scope_then_queue_order(self):
        self.track_two_parties()
        self.assertEqual(self.web_refs(), ["acme/app#2", "acme/app#1", "acme/app#3"])

    def test_item_shape(self):
        self.track_ready("sess-1", 1, "qa/T01", title="Add\nthing")
        self.run_cli(["pr", "set", "acme/app#1", "--needs-human-pr-review"], "sess-1", self.repo_dir)
        self.sync_gh("sess-1")
        self.assertEqual(
            self.model()["ready_for_you"],
            [
                {
                    "ref": "acme/app#1",
                    "title": "Add thing",
                    "url": "https://github.com/acme/app/pull/1",
                    "party": "alpha",
                    "scope": "party:alpha",
                    "scopes": ["party:alpha"],
                    "review_first": True,
                    "checks": "1 passing",
                    "notes": [],
                }
            ],
        )

    def test_pr_in_two_raids_appears_once(self):
        self.track_ready("sess-1", 1, "qa/T01")
        self.sync_gh("sess-1")
        for raid in ("r1", "r2"):
            self.run_cli(["raid", "join", raid, "--until-leave"], "sess-1", self.repo_dir)
        items = self.model()["ready_for_you"]
        self.assertEqual([item["ref"] for item in items], ["acme/app#1"])
        self.assertEqual(sorted(s for s in items[0]["scopes"] if s.startswith("raid:")), ["raid:r1", "raid:r2"])
        self.assertIn(items[0]["scope"], items[0]["scopes"])

    def test_ci_label_note_is_carried(self):
        self._set_project_config({"human_ready": {"ci_label": "run-ci"}})
        self.track_ready("sess-1", 1, "qa/T01", statusCheckRollup=[], labels=[])
        self.sync_gh("sess-1")
        self.assertEqual(self.model()["ready_for_you"][0]["notes"], ["CI label run-ci not on the PR"])


class CliSectionTests(ReadyForYouTestCase):
    def test_nothing_ready(self):
        self.assertIn("READY FOR YOU · nothing", self.board([]))

    def test_section_sits_between_needs_you_and_the_party_blocks(self):
        self.track_two_parties()
        out = self.board([])
        self.assertLess(out.index("NEEDS YOU"), out.index("READY FOR YOU"))
        self.assertLess(out.index("READY FOR YOU"), out.index("alpha"))

    def test_lists_prs_in_queue_order(self):
        self.track_two_parties()
        self.assertEqual(self.section_refs([]), ["acme/app#2", "acme/app#1", "acme/app#3"])
        self.assertIn("READY FOR YOU · 3", self.section([]))

    def test_line_has_title_party_and_review_first(self):
        self.track_ready("sess-1", 1, "qa/T01", title="Add thing")
        self.run_cli(["pr", "set", "acme/app#1", "--needs-human-pr-review"], "sess-1", self.repo_dir)
        self.sync_gh("sess-1")
        self.assertIn("  acme/app#1 Add thing · alpha · review first", self.section([]))

    def test_note_lines_are_indented(self):
        self._set_project_config({"human_ready": {"ci_label": "run-ci"}})
        self.track_ready("sess-1", 1, "qa/T01", statusCheckRollup=[], labels=[])
        self.sync_gh("sess-1")
        self.assertIn("\n    note: CI label run-ci not on the PR", self.section([]))

    def test_party_filter(self):
        self.track_two_parties()
        self.assertEqual(self.section_refs(["--party", "beta"]), ["acme/app#3"])

    def test_raid_filter(self):
        self.track_two_parties()
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-2", self.repo_dir)
        self.assertEqual(self.section_refs(["--raid", "ci"]), ["acme/app#3"])

    def test_raid_filter_on_the_second_raid(self):
        self.track_ready("sess-1", 1, "qa/T01")
        self.sync_gh("sess-1")
        for raid in ("r1", "r2"):
            self.run_cli(["raid", "join", raid, "--until-leave"], "sess-1", self.repo_dir)
        self.assertEqual(self.section_refs(["--raid", "r2"]), ["acme/app#1"])
        self.assertEqual(self.section_refs(["--raid", "r1"]), ["acme/app#1"])


class AcceptanceTests(ReadyForYouTestCase):
    def test_cli_web_and_review_md_list_the_same_prs_in_order(self):
        self.track_two_parties()
        expected = ["acme/app#2", "acme/app#1"]
        self.assertEqual(self.section_refs(["--party", "alpha"]), expected)
        self.assertEqual([i["ref"] for i in self.model()["ready_for_you"] if i["party"] == "alpha"], expected)
        self.assertEqual(_REVIEW_REF_RE.findall(self.review_md(["--party", "alpha"])), expected)
        self.assertEqual(self.section_refs([]), self.web_refs())

    def test_second_raid_matches_across_cli_web_and_review_md(self):
        self.track_ready("sess-1", 1, "qa/T01")
        self.sync_gh("sess-1")
        for raid in ("r1", "r2"):
            self.run_cli(["raid", "join", raid, "--until-leave"], "sess-1", self.repo_dir)
        web = [i["ref"] for i in self.model()["ready_for_you"] if "raid:r2" in i["scopes"]]
        self.assertEqual(web, ["acme/app#1"])
        self.assertEqual(self.section_refs(["--raid", "r2"]), web)
        self.assertEqual(_REVIEW_REF_RE.findall(self.review_md(["--raid", "r2"])), web)
