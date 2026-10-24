import json

from guild import db, paths, task_context
from tests.testutil import GuildTestCase


class _Ctx:
    def __init__(self, conn, case):
        self.conn = conn
        self.projects_dir = case.config_home / "guild" / "projects"


class TaskContextTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.conn = db.connect(paths.db_path())
        self.ctx = _Ctx(self.conn, self)

    def test_task_ref_known(self):
        ref = task_context.task_ref(self.ctx, None, "task:demo/T01")
        self.assertEqual(
            ref,
            {
                "kind": "task",
                "ref": "task:demo/T01",
                "quest": "demo",
                "tid": "T01",
                "title": "First",
                "state": "queued",
                "epic": None,
                "spec": None,
                "tasks": None,
            },
        )

    def test_task_ref_missing(self):
        ref = task_context.task_ref(self.ctx, None, "task:demo/T99")
        self.assertEqual(
            ref, {"kind": "task", "ref": "task:demo/T99", "quest": "demo", "tid": "T99", "missing": True}
        )

    def test_sdd_paths_root(self):
        paths_pair = task_context.sdd_paths({"sdd": {"root": "/r", "epics_dir": "epics"}}, "widget")
        self.assertEqual(paths_pair, ("/r/epics/widget/spec.md", "/r/epics/widget/tasks.md"))

    def test_sdd_paths_git_ref(self):
        paths_pair = task_context.sdd_paths({"sdd": {"git_ref": "origin/main", "epics_dir": "epics"}}, "widget")
        self.assertEqual(
            paths_pair,
            ("git:origin/main:epics/widget/spec.md", "git:origin/main:epics/widget/tasks.md"),
        )

    def test_sdd_paths_without_config_or_epic(self):
        self.assertEqual(task_context.sdd_paths(None, "widget"), (None, None))
        self.assertEqual(task_context.sdd_paths({}, "widget"), (None, None))
        self.assertEqual(task_context.sdd_paths({"sdd": {"root": "/r", "epics_dir": "epics"}}, None), (None, None))

    def test_project_config_known_and_unbound(self):
        project, project_config = task_context.project_config(self.ctx, "alpha")
        self.assertEqual(project, "acme")
        self.assertEqual(project_config["name"], "acme")
        self.assertEqual(task_context.project_config(self.ctx, "nope"), (None, None))

    def test_project_config_unreadable_config_keeps_project(self):
        (self.config_home / "guild" / "projects" / "acme.json").write_text(json.dumps({"name": "acme"}))
        self.assertEqual(task_context.project_config(self.ctx, "alpha"), ("acme", None))
