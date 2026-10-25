import shutil
import unittest
from pathlib import Path

from tests import node_harness

_HARNESS_NAME = "web_resources_harness.js"
_APP_JS = Path(__file__).resolve().parent.parent / "guild" / "web" / "app.js"


def _machine(disk_percent, mem_available, disk_delta, untracked_growth, reclaimable):
    return {
        "sampled_at": "t",
        "disk_percent": disk_percent,
        "disk_used": 1,
        "disk_total": 2,
        "disk_delta": disk_delta,
        "mem_total": 100,
        "mem_available": mem_available,
        "guild_db_bytes": 1,
        "untracked_growth": untracked_growth,
        "docker": {"total": 1, "images_reclaimable": reclaimable},
    }


def _entry(category, item, delta_bytes, new, state, flag):
    return {
        "category": category,
        "item": item,
        "bytes": 5,
        "delta_bytes": delta_bytes,
        "new": new,
        "state": state,
        "flag": flag,
        "detail": "",
    }


def _model(machine, items):
    categories = [{"category": "worktree", "bytes": 5, "delta_bytes": 1, "state": "ok", "detail": ""}]
    project = {
        "name": "acme",
        "baseline_at": "b",
        "total_bytes": 5,
        "delta_bytes": -1,
        "categories": categories,
        "items": items,
        "growers": [],
    }
    return {"since": "1d", "machine": machine, "projects": [project], "unattributed": None}


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebResourceColourTests(unittest.TestCase):
    def _render(self, machine, items):
        return node_harness.request(_HARNESS_NAME, {"src": str(_APP_JS), "model": _model(machine, items)})

    def _class_of(self, pills, text_part):
        matching = [entry["cls"] for entry in pills if text_part in entry["text"]]
        self.assertEqual(len(matching), 1, pills)
        return matching[0]

    def _disk(self, percent):
        rendered = self._render(_machine(percent, 50, 0, 0, 0), [])
        return self._class_of(rendered["resources"], "disk " + str(percent) + "%"), rendered["sidebar"]

    def test_disk_thresholds(self):
        self.assertEqual(self._disk(50)[0], "pill res-ok")
        self.assertEqual(self._disk(80)[0], "pill res-warn")
        self.assertEqual(self._disk(90)[0], "pill res-bad")

    def test_sidebar_shows_the_disk_pill(self):
        _, sidebar = self._disk(90)
        self.assertEqual(sidebar, [{"text": "disk 90%", "cls": "pill res-bad"}])

    def test_ram_thresholds(self):
        for available, expected in ((5, "pill res-bad"), (20, "pill res-warn"), (60, "pill res-ok")):
            rendered = self._render(_machine(10, available, 0, 0, 0), [])
            self.assertEqual(self._class_of(rendered["resources"], "ram"), expected)

    def test_machine_deltas_and_docker(self):
        rendered = self._render(_machine(10, 50, 5, -5, 7), [])["resources"]
        self.assertEqual(self._class_of(rendered, "in 1d"), "pill res-warn")
        self.assertEqual(self._class_of(rendered, "untracked growth"), "pill res-ok")
        self.assertEqual(self._class_of(rendered, "docker"), "pill res-warn")

    def test_project_category_and_item_values(self):
        items = [
            _entry("worktree", "grown", 3, False, "ok", "merged"),
            _entry("worktree", "shrunk", -3, False, "ok", ""),
            _entry("worktree", "fresh", 3, True, "ok", ""),
            _entry("worktree", "gone", None, False, "missing", ""),
        ]
        pills = self._render(_machine(10, 50, 0, 0, 0), items)["resources"]
        self.assertEqual(self._class_of(pills, "merged, still on disk"), "pill res-warn")
        self.assertEqual(self._class_of(pills, "-3 B"), "pill res-ok")
        self.assertEqual(self._class_of(pills, "new"), "pill res-warn")
        self.assertEqual(self._class_of(pills, "missing"), "pill res-dim")
        self.assertEqual(self._class_of(pills, "+1 B"), "pill res-warn")
        self.assertEqual(self._class_of(pills, "-1 B"), "pill res-ok")

    def test_no_machine_leaves_the_sidebar_empty(self):
        rendered = node_harness.request(
            _HARNESS_NAME,
            {"src": str(_APP_JS), "model": {"since": "1d", "machine": None, "projects": [], "unattributed": None}},
        )
        self.assertEqual(rendered["sidebar"], [])


if __name__ == "__main__":
    unittest.main()
