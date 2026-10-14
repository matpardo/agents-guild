import unittest
from datetime import date
from pathlib import Path

from guild.adapters import sdd

_SDD_ROOT = Path(__file__).resolve().parent.parent / "sdd"
_EPICS_DIR = _SDD_ROOT / "epics"
_DECISIONS_DIR = _SDD_ROOT / "decisions"
_README = (_SDD_ROOT.parent / "README.md").read_text()
_GUILD_MD = (_SDD_ROOT.parent / "GUILD.md").read_text()
_NEW_VOCABULARY = "20261004_vocabulary-short-sessions"
_STATUSES = {"draft", "active", "done", "archived"}
_SPEC_KEYS = {"epic", "type", "title", "status", "owner", "created", "updated"}
_CHILD_KEYS = {"epic", "type", "title", "status", "updated"}
_PATTERNS = {
    "task_heading": r"^#{2,3}\s+(T\d+\w*)\b.*?\s[—–-]\s+(.+)$",
    "key_ref": r"#\d+",
    "deps_line": r"^\*\*Depends on:\*\*\s*(.+)$",
    "status_line": r"^\*\*Status:\*\*\s*(.+)$",
}


def _frontmatter(path):
    lines = path.read_text().splitlines()
    if not lines or lines[0] != "---":
        raise AssertionError("{} does not start with frontmatter".format(path))
    end = lines.index("---", 1)
    fields = {}
    for line in lines[1:end]:
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _epic_dirs():
    return sorted(path for path in _EPICS_DIR.iterdir() if path.is_dir())


class SddDocsTests(unittest.TestCase):
    def test_epics_exist(self):
        self.assertTrue(_epic_dirs())

    def test_spec_frontmatter(self):
        for epic_dir in _epic_dirs():
            with self.subTest(epic=epic_dir.name):
                spec = _frontmatter(epic_dir / "spec.md")
                self.assertEqual(set(spec), _SPEC_KEYS)
                self.assertEqual(spec["epic"], epic_dir.name)
                self.assertEqual(spec["type"], "spec")
                self.assertIn(spec["status"], _STATUSES)
                self.assertGreaterEqual(
                    date.fromisoformat(spec["updated"]), date.fromisoformat(spec["created"])
                )

    def test_child_documents_inherit_from_spec(self):
        for epic_dir in _epic_dirs():
            spec = _frontmatter(epic_dir / "spec.md")
            for name in ("tasks", "discovery"):
                path = epic_dir / "{}.md".format(name)
                if not path.exists():
                    continue
                with self.subTest(document=str(path.relative_to(_SDD_ROOT))):
                    child = _frontmatter(path)
                    self.assertEqual(set(child), _CHILD_KEYS)
                    self.assertEqual(child["epic"], epic_dir.name)
                    self.assertEqual(child["type"], name)
                    self.assertEqual(child["status"], spec["status"])
                    self.assertEqual(child["title"], spec["title"])
                    date.fromisoformat(child["updated"])

    def test_active_and_done_epics_have_parseable_tasks(self):
        for epic_dir in _epic_dirs():
            status = _frontmatter(epic_dir / "spec.md")["status"]
            if status not in ("active", "done"):
                continue
            with self.subTest(epic=epic_dir.name):
                tasks = sdd.parse_tasks_file(epic_dir / "tasks.md", _PATTERNS)
                self.assertTrue(tasks)
                tids = {task["tid"] for task in tasks}
                for task in tasks:
                    self.assertTrue(set(task["deps"]) <= tids, task["tid"])
                if status == "done":
                    pending = [task["tid"] for task in tasks if task["sdd_status"] != "done"]
                    self.assertEqual(pending, [])


class VocabularyDecisionTests(unittest.TestCase):
    def test_old_vocabulary_points_at_the_new_one(self):
        old = (_DECISIONS_DIR / "20260927_vocabulary.md").read_text()
        self.assertIn("- **Status:** superseded by {}".format(_NEW_VOCABULARY), old)

    def test_new_vocabulary_is_accepted_and_names_every_term(self):
        new = (_DECISIONS_DIR / "{}.md".format(_NEW_VOCABULARY)).read_text()
        self.assertIn("- **Status:** accepted", new)
        self.assertIn("Supersedes `20260927_vocabulary`", new)
        for term in ("guild", "party", "leader", "generation", "keeper", "quest", "raid lead", "brief"):
            self.assertIn("| {} |".format(term), new)

    def test_readme_glossary_matches(self):
        glossary = _README.split("## Glossary")[1].split("## Install")[0]
        self.assertIn("the live session of a party: zero or one", glossary)
        for term in ("generation", "keeper", "raid lead", "brief"):
            self.assertIn("- **{}**".format(term), glossary)


class EphemeralBriefDocsTests(unittest.TestCase):
    def test_epic_has_its_tasks(self):
        epic_dir = _EPICS_DIR / "ephemeral-brief"
        self.assertIn(_frontmatter(epic_dir / "spec.md")["status"], ("active", "done"))
        tasks = sdd.parse_tasks_file(epic_dir / "tasks.md", _PATTERNS)
        self.assertEqual([task["tid"] for task in tasks], ["T01", "T02", "T03", "T04", "T05", "T06"])

    def test_readme_documents_the_task_brief(self):
        self.assertIn(
            "guild brief [<party>/<quest>/<tid>]   # no argument: per-session view;"
            " with a task: read-only, budgeted brief for a fresh session",
            _README,
        )
        self.assertIn("### Task brief", _README)
        self.assertIn("'Continue the work described in the guild brief.'", _README)
        self.assertNotIn("described in the guild handoff", _README)
        self.assertIn("Recommended: 40, so sessions stay short and each fresh generation starts from the brief.", _README)
        self.assertIn('"handoff_threshold": 40,', _README)

    def test_guild_md_says_sessions_are_short(self):
        self.assertIn(
            "Sessions are meant to be short: the new session starts from"
            " `guild brief <party>/<quest>/<tid>`, injected for you at session start.",
            _GUILD_MD,
        )


class DispatcherDocsTests(unittest.TestCase):
    _decision = _DECISIONS_DIR / "20261012_dispatcher-suggests-human-launches.md"
    _superseded = _DECISIONS_DIR / "20261004_dispatcher-launches-fresh-sessions.md"

    def test_epic_is_active_with_all_its_tasks(self):
        epic_dir = _EPICS_DIR / "dispatcher"
        self.assertEqual(_frontmatter(epic_dir / "spec.md")["status"], "active")
        tasks = sdd.parse_tasks_file(epic_dir / "tasks.md", _PATTERNS)
        self.assertEqual([task["tid"] for task in tasks], ["T{:02d}".format(number) for number in range(1, 24)])
        by_tid = {task["tid"]: task["sdd_status"] for task in tasks}
        for tid in ("T10", "T11", "T12", "T13"):
            self.assertEqual(by_tid[tid], "done")

    def test_decision_is_superseded_and_names_the_guards(self):
        text = self._decision.read_text()
        self.assertIn("- **Status:** superseded by 20261014_board-shows-waits-no-dispatcher", text)
        self.assertIn("- **Supersedes:** 20261004_dispatcher-launches-fresh-sessions", text)
        self.assertIn("No session starts or wakes on its own.", text)
        self.assertIn("deferred and retried for 24 hours", text)
        self.assertIn("`20260928_idle-wake-no-go` now holds fully", text)
        self.assertIn("Lifecycle commands stay in `sync`.", text)
        self.assertIn(
            "- **Status:** superseded by 20261012_dispatcher-suggests-human-launches", self._superseded.read_text()
        )

    def test_readme_documents_the_dispatcher(self):
        self.assertIn("guild dispatch run [--dry-run]", _README)
        self.assertIn("guild dispatch status", _README)
        self.assertIn("guild dispatch-timer install --every <dur> | uninstall | print", _README)
        self.assertIn("### Dispatcher", _README)
        self.assertIn('"dispatcher": {"rules": {"ask_answered": "on"', _README)
        self.assertIn("`dispatch-failed`", _README)
        self.assertIn("`deferred`", _README)
        self.assertIn("`NoNewPrivileges=yes` and `Nice=10`", _README)
        self.assertIn("`dispatcher` (active: suggests a revive", _README)

    def test_guild_md_tells_sessions_how_to_wait_for_the_dispatcher(self):
        self.assertIn("**Blocked on an ask with nothing else to do?**", _GUILD_MD)
        self.assertIn("where the project enables the dispatcher, the human is told to run `guild revive --party <party>`", _GUILD_MD)


if __name__ == "__main__":
    unittest.main()
