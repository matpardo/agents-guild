import json
import sqlite3

from tests.testutil import GuildTestCase

TASKS_MD = """---
epic: demo-epic
type: tasks
title: Demo Epic
status: active
updated: 2026-09-29
---

# Tasks

## T01 — First

**Deps:** T02
**Status:** [ ] pending

## T02 — Second

**Deps:** —
**Status:** [ ] pending

## T03 — Third

**Deps:** —
**Status:** [ ] pending
"""

OPEN_VIEW = {
    "state": "OPEN",
    "isDraft": False,
    "headRefName": "feature/x",
    "title": "t",
    "statusCheckRollup": [{"conclusion": "SUCCESS"}],
    "mergeable": "MERGEABLE",
}


def diff_fixture(paths, additions, deletions, created_at):
    return {
        "files": [{"path": path} for path in paths],
        "additions": additions,
        "deletions": deletions,
        "createdAt": created_at,
    }


class MergeQueueTestCase(GuildTestCase):
    def mark_billing_blocked(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.execute(
            "INSERT INTO main_status (repo, source, red, reason, external, updated_at)"
            " VALUES ('acme/app', 'gh', 1, 'checks failing: lint', 'billing', '2026-01-01T00:00:00Z')"
        )
        conn.commit()
        conn.close()

    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self._set_project_config(
            {"shared_areas": ["config/locales/es.yml", "shared/**"], "shared_area_claim_ttl": "2h"}
        )

    def _set_project_config(self, extra):
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data.update(extra)
        config_file.write_text(json.dumps(data))

    def start_party(self, name, session_id):
        self.run_cli(
            ["party", "start", name, "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            session_id,
            self.repo_dir,
        )

    def add_quest(self, session_id, slug, epic, tasks):
        code, out, err = self.run_cli(
            ["quest", "add", slug, "--title", slug, "--epic", epic, "--tasks", tasks],
            session_id,
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)

    def track(self, session_id, number, task, lifecycle):
        self.write_gh_fixture("view_acme-app_{}".format(number), dict(OPEN_VIEW, isDraft=lifecycle != "ready"))
        code, out, err = self.run_cli(
            [
                "pr",
                "track",
                "acme/app#{}".format(number),
                "--task",
                task,
                "--what",
                "pr {}".format(number),
                "--waits",
                "review",
            ],
            session_id,
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(
            ["pr", "set", "acme/app#{}".format(number), "--lifecycle", lifecycle], session_id, self.repo_dir
        )
        self.assertEqual(code, 0, err)

    def sync_gh(self, session_id):
        return self.run_cli(["sync", "--source", "gh"], session_id, self.repo_dir)

    def query(self, sql):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql).fetchall()
        conn.close()
        return rows
