import unittest
from pathlib import Path

from guild.adapters import sdd

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sdd"

_PATTERNS = {
    "task_heading": r"^#{2,3}\s+(T\d+\w*)\b.*?\s[—–-]\s+(.+)$",
    "key_ref": r"[A-Z]{2,10}-\d+",
    "deps_line": r"^\*\*Deps:\*\*\s*(.+)$",
    "status_line": r"^\*\*Status:\*\*\s*(.+)$",
}

_PATTERNS_WITH_ORDER = dict(_PATTERNS, order_list=r"^\d+\.\s+(.+)$")


def _parse(name, patterns):
    return sdd.parse_tasks_file(_FIXTURES / name, patterns)


class DominantShapeTests(unittest.TestCase):
    def test_parses_plain_dash_heading(self):
        tasks = _parse("dominant.md", _PATTERNS)
        self.assertEqual([t["tid"] for t in tasks], ["T01", "T02"])
        self.assertEqual(tasks[0]["title"], "Configure retries")
        self.assertIsNone(tasks[0]["jira_key"])
        self.assertEqual(tasks[0]["deps"], [])
        self.assertEqual(tasks[0]["sdd_status"], "done")
        self.assertEqual(tasks[1]["deps"], ["T01"])
        self.assertEqual(tasks[1]["sdd_status"], "pending")


class KeyRefShapeTests(unittest.TestCase):
    def test_title_keeps_hyphens_after_first_separator(self):
        text = (
            "## T01 — Cross-tenant owner lookup (DEMO-186)\n\n"
            "**Deps:** —\n\n**Status:** [ ] pending\n\n"
            "### T02 → DEMO-7 — Feature-namespace guide\n\n"
            "**Deps:** T01\n\n**Status:** [x] done\n"
        )
        tasks = sdd.parse_tasks_text(text, _PATTERNS)
        self.assertEqual(tasks[0]["title"], "Cross-tenant owner lookup (DEMO-186)")
        self.assertEqual(tasks[0]["jira_key"], "DEMO-186")
        self.assertEqual(tasks[1]["title"], "Feature-namespace guide")
        self.assertEqual(tasks[1]["jira_key"], "DEMO-7")

    def test_parses_arrow_key_heading(self):
        tasks = _parse("key_arrow.md", _PATTERNS)
        self.assertEqual(tasks[0]["title"], "Add validation")
        self.assertEqual(tasks[0]["jira_key"], "ACME-71")

    def test_parses_parens_key_heading(self):
        tasks = _parse("key_parens.md", _PATTERNS)
        self.assertEqual(tasks[0]["title"], "Improve caching")
        self.assertEqual(tasks[0]["jira_key"], "ACME-9")


class DepsParsingTests(unittest.TestCase):
    def test_deps_with_prose_suffix_extracts_tids_only(self):
        tasks = _parse("deps_prose.md", _PATTERNS)
        by_tid = {t["tid"]: t for t in tasks}
        self.assertEqual(by_tid["T02"]["deps"], ["T01", "T14"])

    def test_repeated_tid_in_prose_is_deduped(self):
        tasks = sdd.parse_tasks_text(
            "## T02 — Ship feature flag\n\n"
            "**Deps:** T01 (gate — needs T01 merged first), T14\n\n"
            "**Status:** [ ] pending\n",
            _PATTERNS,
        )
        self.assertEqual(tasks[0]["deps"], ["T01", "T14"])

    def test_em_dash_alone_means_no_deps(self):
        tasks = _parse("deps_none.md", _PATTERNS)
        self.assertEqual(tasks[0]["deps"], [])


class OrderListTests(unittest.TestCase):
    def test_order_list_reorders_tasks(self):
        tasks = _parse("order_list.md", _PATTERNS_WITH_ORDER)
        by_tid = {t["tid"]: t for t in tasks}
        self.assertEqual(by_tid["T02"]["order_idx"], 0)
        self.assertEqual(by_tid["T01"]["order_idx"], 1)

    def test_order_idx_none_when_order_list_not_configured(self):
        tasks = _parse("order_list.md", _PATTERNS)
        for task in tasks:
            self.assertIsNone(task["order_idx"])


class SuffixedTidTests(unittest.TestCase):
    def test_suffixed_tid_parses_as_its_own_task(self):
        tasks = _parse("suffixed_tid.md", _PATTERNS)
        self.assertEqual(tasks[0]["tid"], "T09b")
        self.assertEqual(tasks[0]["deps"], ["T09"])


class UnparseableFileTests(unittest.TestCase):
    def test_zero_matching_headings_is_unparseable(self):
        result = _parse("unparseable.md", _PATTERNS)
        self.assertIsNone(result)


class DiscoverEpicFilesTests(unittest.TestCase):
    def test_discovers_epic_directories_with_tasks_md(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "epics" / "widget-rollout").mkdir(parents=True)
            (root / "epics" / "widget-rollout" / "tasks.md").write_text("## T01 — x\n")
            (root / "epics" / "no-tasks-file").mkdir(parents=True)
            files = sdd.discover_epic_files(root, "epics")
            self.assertEqual([name for name, _ in files], ["widget-rollout"])

    def test_returns_empty_list_when_epics_dir_missing(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sdd.discover_epic_files(Path(tmp), "epics"), [])


if __name__ == "__main__":
    unittest.main()
