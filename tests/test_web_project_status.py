import json
from pathlib import Path

from guild.commands import board as board_commands
from tests.test_web_board_model import _TASKS_MD, BoardModelTestCase

_VIEW = {
    "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
    "statusCheckRollup": [{"conclusion": "SUCCESS"}], "mergeable": "MERGEABLE",
}
_APP_JS = (Path(__file__).resolve().parent.parent / "guild" / "web" / "app.js").read_text()


class ProjectStatusTestCase(BoardModelTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def _configure(self, **values):
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data.update(values)
        config_file.write_text(json.dumps(data))

    def _track(self, number):
        self.write_gh_fixture("view_acme-app_{}".format(number), _VIEW)
        code, _, err = self.run_cli(
            ["pr", "track", "acme/app#{}".format(number), "--card", "ACME-{}".format(number),
             "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0, err)

    def _touch(self, number, path):
        ctx = self._ctx()
        ctx.conn.execute("INSERT INTO pr_files (repo, number, path) VALUES ('acme/app', ?, ?)", (number, path))
        ctx.conn.commit()

    def _model(self):
        return board_commands.board_model(self._ctx())

    def _board(self):
        return "\n".join(board_commands.render_board(self._ctx(), None, None, False, 100))


class CapsTests(ProjectStatusTestCase):
    def test_party_and_project_caps(self):
        self._configure(max_open_prs_per_party=1, max_open_prs=2)
        self._track(1)
        model = self._model()
        self.assertEqual(
            model["parties"][0]["caps"],
            {"open": 1, "cap": 1, "wait": "wait: 1 open PRs, merge acme/app#1 first"},
        )
        project = model["projects"][0]
        self.assertEqual((project["open_prs"], project["max_open_prs"], project["wait"]), (1, 2, None))
        self.assertIn("open PRs: 1/1", self._board())
        self.assertIn("open PRs: 1/2", self._board())
        self._track(2)
        self.assertEqual(
            self._model()["projects"][0]["wait"], "wait: 2 open PRs in project, merge acme/app#1 first"
        )

    def test_no_caps_configured(self):
        model = self._model()
        self.assertEqual(model["parties"][0]["caps"], {"open": 0, "cap": None, "wait": None})
        self.assertEqual(model["projects"][0]["max_open_prs"], None)
        self.assertNotIn("open PRs:", self._board())

    def test_external_block_not_counted(self):
        self._configure(max_open_prs=1)
        self._track(1)
        self.run_cli(["pr", "set", "acme/app#1", "--blocked-external", "vendor"], "sess-1", self.repo_dir)
        self.assertEqual(self._model()["projects"][0]["open_prs"], 0)


class HotFilesTests(ProjectStatusTestCase):
    def test_hot_file_lists_prs_at_cap(self):
        self._configure(max_open_prs_per_file=2)
        for number in (1, 2):
            self._track(number)
            self._touch(number, "a.py")
        self._touch(1, "b.py")
        hot = self._model()["projects"][0]["hot_files"]
        self.assertEqual(hot, [{"repo": "acme/app", "path": "a.py", "prs": ["acme/app#1", "acme/app#2"]}])
        self.assertIn("hot file: acme/app a.py: acme/app#1, acme/app#2", self._board())

    def test_hidden_when_feature_off(self):
        for number in (1, 2):
            self._track(number)
            self._touch(number, "a.py")
        self.assertEqual(self._model()["projects"][0]["hot_files"], [])
        self.assertNotIn("hot file", self._board())

    def test_empty_below_cap(self):
        self._configure(max_open_prs_per_file=3)
        for number in (1, 2):
            self._track(number)
            self._touch(number, "a.py")
        self.assertEqual(self._model()["projects"][0]["hot_files"], [])


class FindingClassesTests(ProjectStatusTestCase):
    def _record(self, number, cls):
        return self.run_cli(
            ["finding", "record", "acme/app#{}".format(number), "--class", cls], "sess-1", self.repo_dir
        )

    def test_classes_with_threshold(self):
        self._configure(finding_guard_threshold=2)
        self._record(1, "mask")
        self._record(2, "mask")
        self._record(3, "audit")
        classes = self._model()["projects"][0]["finding_classes"]
        self.assertEqual(
            classes,
            [
                {"class": "mask", "count": 2, "threshold": 2, "at_threshold": True},
                {"class": "audit", "count": 1, "threshold": 2, "at_threshold": False},
            ],
        )
        self.assertIn("finding class: mask 2 PR(s) (at threshold)", self._board())

    def test_cli_list(self):
        self._configure(finding_guard_threshold=2)
        self._record(1, "mask")
        self._record(2, "mask")
        self._record(3, "audit")
        code, out, _ = self.run_cli(["finding", "list"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip().splitlines(), ["mask: 2 PR(s) (at threshold 2)", "audit: 1 PR(s)"])

    def test_cli_list_empty(self):
        code, out, _ = self.run_cli(["finding", "list"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        self.assertIn("no finding classes in acme", out)

    def test_empty_model(self):
        self.assertEqual(self._model()["projects"][0]["finding_classes"], [])


class FreshnessTests(ProjectStatusTestCase):
    def test_never_synced(self):
        self.assertEqual(self._model()["projects"][0]["freshness"], {"sdd": None, "tracker": None})
        self.assertIn("sdd synced never, tracker synced never", self._board())

    def test_sdd_synced(self):
        code, _, err = self.sync_sdd(self.repo_dir, "sess-1", "acme", "demo-epic", _TASKS_MD)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._model()["projects"][0]["freshness"], {"sdd": "0s", "tracker": None})
        self.assertIn("sdd synced 0s ago, tracker synced never", self._board())


class WebWiringTests(ProjectStatusTestCase):
    def test_app_renders_projects_and_caps(self):
        for token in ("[filtered.projects], renderProjects", "party.caps", "hot_files", "finding_classes", "freshness"):
            with self.subTest(token=token):
                self.assertIn(token, _APP_JS)

    def test_queue_reason_pills_get_tooltips(self):
        for token in ('"checks failing"', '"needs ask answer"', '"waits on task"'):
            with self.subTest(token=token):
                self.assertIn(token, _APP_JS)
