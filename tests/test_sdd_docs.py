import unittest
from datetime import date
from pathlib import Path

from guild.adapters import sdd

_SDD_ROOT = Path(__file__).resolve().parent.parent / "sdd"
_EPICS_DIR = _SDD_ROOT / "epics"
_STATUSES = {"active", "done", "archived"}
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


if __name__ == "__main__":
    unittest.main()
