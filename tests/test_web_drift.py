import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from guild import context, db, paths, timeutil
from guild.commands import board as board_commands
from tests.test_party_drift import PartyDriftTestCase

_APP_JS_PATH = Path(__file__).resolve().parent.parent / "guild" / "web" / "app.js"
_APP_JS = _APP_JS_PATH.read_text()


class WebDriftModelTests(PartyDriftTestCase):
    def _model(self):
        conn = db.connect(paths.db_path())
        ctx = context.RunContext(
            conn, None, None, timeutil.utcnow(), None,
            paths.claude_sessions_dir(), paths.projects_config_dir(), paths.state_dir(),
        )
        model = board_commands.board_model(ctx)
        conn.close()
        return model

    def _parties(self, model):
        return {party["name"]: party for party in model["parties"]}

    def test_board_findings_carry_the_owning_party(self):
        self._record_cards([self._card("DEMO-90", "new")])
        self._start_task()
        findings = self._model()["drift"][0]["findings"]["task started, card not started"]
        self.assertEqual([finding["party"] for finding in findings], ["alpha"])
        self.assertIn("move DEMO-90 to In Progress", findings[0]["text"])

    def test_finding_without_a_party_carries_none(self):
        self._record_cards([self._card("DEMO-90", "done", status="Done")])
        findings = self._model()["drift"][0]["findings"]["tracker and SDD disagree"]
        self.assertEqual([finding["party"] for finding in findings], [None])

    def test_party_card_lists_its_own_drift_only(self):
        self._record_cards([self._card("DEMO-90", "new")])
        self._start_task()
        parties = self._parties(self._model())
        self.assertEqual(len(parties["alpha"]["drift"]["findings"]), 1)
        self.assertEqual(parties["alpha"]["drift"]["more"], 0)
        self.assertEqual(parties["beta"]["drift"], {"findings": [], "more": 0})

    def test_party_card_drift_is_capped_with_a_more_count(self):
        self._record_cards([self._card("DEMO-90", "new")])
        for number in range(1, 8):
            self._track_pr(number, "wave9", "T01")
        drift = self._parties(self._model())["alpha"]["drift"]
        self.assertEqual((len(drift["findings"]), drift["more"]), (5, 2))


class WebDriftScriptTests(unittest.TestCase):
    def test_drift_follows_the_party_and_raid_filters(self):
        self.assertIn("drift: filterDriftByParties(data.drift, [state.partyFilter])", _APP_JS)
        self.assertIn("drift: filterDriftByParties(data.drift, members)", _APP_JS)
        self.assertIn("finding.party !== null && parties.indexOf(finding.party) !== -1", _APP_JS)

    def test_party_card_renders_its_drift_with_a_more_line(self):
        self.assertIn("renderPartyDrift(party.drift)", _APP_JS)
        self.assertIn('partyDrift.more + " more"', _APP_JS)

    def test_renders_finding_text(self):
        self.assertTrue(re.search(r'textEl\("li", finding\.text\)', _APP_JS))


_HARNESS = Path(__file__).resolve().parent / "web_drift_harness.js"
_BOARD = {
    "generated_at": "now", "asks": [], "notices": [], "blocked": [], "merge_queues": [],
    "dispatcher": {"in_flight": [], "failed": [], "projects": [], "deferred": [], "recent": []}, "projects": [], "raids": [{"name": "r", "members": ["c"]}],
    "parties": [
        {
            "name": name, "raids": [], "quests": [], "prs": [], "claims": [], "state": "active", "generation": 1,
            "status": {"name": "idle", "label": "idle"}, "remaining": {"all_done": True}, "ctx": None,
            "resume_command": None, "caps": None, "drift": {"findings": [], "more": 0}, "leader_session_name": None,
        }
        for name in ("a", "c")
    ],
    "drift": [{
        "project": "p", "scope": "scope: x",
        "findings": {
            "rule1": [{"text": "FA", "party": "a"}, {"text": "FC", "party": "c"}, {"text": "FN", "party": None}],
            "rule2": [{"text": "FC2", "party": "c"}],
        },
    }],
}


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebDriftBehaviorTests(unittest.TestCase):
    def _rendered(self, party_filter, raid_filter):
        with tempfile.TemporaryDirectory() as tmp:
            board = Path(tmp) / "board.json"
            board.write_text(json.dumps(_BOARD))
            result = subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(board), party_filter, raid_filter],
                capture_output=True, text=True, timeout=30, check=True,
            )
        return result.stdout.strip()

    def test_no_filter_shows_every_finding(self):
        self.assertEqual(self._rendered("all", "all"), "drift p scope: x rule1 (3) FA FC FN rule2 (1) FC2")

    def test_party_filter_keeps_only_that_party(self):
        self.assertEqual(self._rendered("a", "all"), "drift p scope: x rule1 (1) FA")

    def test_raid_filter_keeps_member_findings_and_drops_empty_rules(self):
        self.assertEqual(self._rendered("all", "r"), "drift p scope: x rule1 (1) FC rule2 (1) FC2")

    def test_party_without_findings_shows_no_drift(self):
        board = dict(_BOARD, drift=[{"project": "p", "scope": "scope: x", "findings": {"rule1": [{"text": "FC", "party": "c"}]}}])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps(board))
            out = subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(path), "a", "all"],
                capture_output=True, text=True, timeout=30, check=True,
            ).stdout.strip()
        self.assertEqual(out, "drift p scope: x no drift")

    def test_party_filter_renders_a_board_with_a_merge_queue(self):
        entry = {
            "ref": "o/r#1", "repo": "o/r", "number": 1, "party": "a", "task": "q/T1", "lifecycle": "ready",
            "branch": "b", "checks_failing": 0, "checks_passing": 1, "checks_pending": 0, "labels": [],
            "url": "https://example.test/1", "position": 1, "unblocks": 0, "state": "ready", "next_action": False,
            "action": "merge", "why": "ready", "reasons": [], "blockers": [], "waits": [], "gates": [],
        }
        queue = {"head": None, "scope": "party:a", "synced_at": "now", "synced_label": "synced now", "main": [], "queue": [entry]}
        board = dict(_BOARD, merge_queues=[queue])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps(board))
            out = subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(path), "a", "all"],
                capture_output=True, text=True, timeout=30, check=True,
            ).stdout.strip()
        self.assertEqual(out, "drift p scope: x rule1 (1) FA")


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebQueueBlockBehaviorTests(unittest.TestCase):
    def _queue_text(self, blocked_external):
        labels = [] if blocked_external is None else ["blocked-external"]
        entry = {
            "ref": "o/r#1", "repo": "o/r", "number": 1, "party": "a", "task": "q/T1", "lifecycle": "ready",
            "branch": "b", "checks_failing": 0, "checks_passing": 1, "checks_pending": 0, "labels": labels,
            "blocked_external": blocked_external, "url": "https://example.test/1", "position": 1, "unblocks": 0,
            "state": "ready", "next_action": False, "action": "merge", "why": "ready", "reasons": [], "blockers": [],
            "waits": [], "gates": [],
        }
        queue = {"head": None, "scope": "party:a", "synced_at": "now", "synced_label": "synced now", "main": [], "queue": [entry]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps(dict(_BOARD, merge_queues=[queue])))
            return subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(path), "all", "all", "merge-queues"],
                capture_output=True, text=True, timeout=30, check=True,
            ).stdout

    def test_queue_entry_offers_block(self):
        text = self._queue_text(None)
        self.assertIn("Block", text)
        self.assertNotIn("Unblock", text)

    def test_blocked_queue_entry_offers_unblock_and_shows_the_reason(self):
        text = self._queue_text("waiting on legal")
        self.assertIn("Unblock", text)
        self.assertIn("waiting on legal", text)
