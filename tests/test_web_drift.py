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
_MISSING = object()
_BOARD = {
    "generated_at": "now", "asks": [], "notices": [], "blocked": [], "merge_queues": [],
    "dispatcher": {"in_flight": [], "failed": [], "projects": [], "deferred": [], "recent": [], "paused": None}, "projects": [], "raids": [{"name": "r", "members": ["c"]}],
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
            "branch": "b", "checks_failing": 0, "checks_passing": 1, "checks_pending": 0, "labels": [], "fix_reasons": [], "fix_request": None,
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
        labels = [] if blocked_external in (None, _MISSING) else ["blocked-external"]
        entry = {
            "ref": "o/r#1", "repo": "o/r", "number": 1, "party": "a", "task": "q/T1", "lifecycle": "ready",
            "branch": "b", "checks_failing": 0, "checks_passing": 1, "checks_pending": 0, "labels": labels, "fix_reasons": [], "fix_request": None,
            "url": "https://example.test/1", "position": 1, "unblocks": 0,
            "state": "ready", "next_action": False, "action": "merge", "why": "ready", "reasons": [], "blockers": [],
            "waits": [], "gates": [],
        }
        if blocked_external is not _MISSING:
            entry["blocked_external"] = blocked_external
        queue = {"head": None, "scope": "party:a", "synced_at": "now", "synced_label": "synced now", "main": [], "queue": [entry]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps(dict(_BOARD, merge_queues=[queue])))
            return subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(path), "all", "all", "merge-queues"],
                capture_output=True, text=True, timeout=30, check=True,
            ).stdout

    def test_entry_without_the_field_offers_block_manually(self):
        text = self._queue_text(_MISSING)
        self.assertIn("Block manually", text)
        self.assertNotIn("Unblock", text)

    def test_null_entry_offers_block_manually(self):
        text = self._queue_text(None)
        self.assertIn("Block manually", text)
        self.assertNotIn("Unblock", text)

    def test_blocked_queue_entry_offers_unblock_and_shows_the_reason(self):
        text = self._queue_text("waiting on legal")
        self.assertIn("Unblock", text)
        self.assertIn("waiting on legal", text)
        self.assertIn("blocked: manual", text)
        self.assertNotIn("Block manually", text)


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebQueueAskFixBehaviorTests(unittest.TestCase):
    def _queue_text(self, blocked_external, fix_reasons, fix_request):
        entry = {
            "ref": "o/r#1", "repo": "o/r", "number": 1, "party": "a", "task": "q/T1", "lifecycle": "ready",
            "branch": "b", "checks_failing": 1, "checks_passing": 0, "checks_pending": 0, "labels": [],
            "url": "https://example.test/1", "position": 1, "unblocks": 0, "state": "blocked", "next_action": False,
            "action": "fix", "why": "", "reasons": fix_reasons, "blockers": fix_reasons, "waits": [], "gates": [],
            "blocked_external": blocked_external, "fix_reasons": fix_reasons,
            "fix_request": fix_request,
        }
        queue = {"head": None, "scope": "party:a", "synced_at": "now", "synced_label": "synced now", "main": [], "queue": [entry]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps(dict(_BOARD, merge_queues=[queue])))
            return subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(path), "all", "all", "merge-queues"],
                capture_output=True, text=True, timeout=30, check=True,
            ).stdout

    def test_auto_blocked_entry_names_the_party_in_the_button(self):
        text = self._queue_text(None, ["checks failing (1)"], None)
        self.assertIn("Ask a to fix", text)
        self.assertNotIn("fixing", text)

    def test_entry_without_automatic_blockers_has_no_button(self):
        self.assertNotIn("to fix", self._queue_text(None, [], None))

    def test_manually_blocked_entry_has_no_button(self):
        self.assertNotIn("to fix", self._queue_text("legal", ["checks failing (1)"], None))

    def test_open_request_shows_the_pill_instead_of_the_button(self):
        request = {"party": "a", "at": "2026-10-11T10:00:00+00:00", "age_hours": 3, "stale": False}
        text = self._queue_text(None, ["checks failing (1)"], request)
        self.assertIn("fixing \u00b7 a \u00b7 3h", text)
        self.assertIn("clears when the blockers are gone", _APP_JS_PATH.read_text())
        self.assertNotIn("to fix\"", text)
        self.assertNotIn("Ask a", text)

    def test_stale_request_shows_the_stale_pill_and_asks_again(self):
        request = {"party": "a", "at": "2026-10-11T10:00:00+00:00", "age_hours": 30, "stale": True}
        text = self._queue_text(None, ["checks failing (1)"], request)
        self.assertIn("fixing \u00b7 stale", text)
        self.assertIn("Ask a again", text)


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebNoticeAndRaidBehaviorTests(unittest.TestCase):
    def _rendered(self, board, out_id):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps(board))
            return subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(path), "all", "all", out_id],
                capture_output=True, text=True, timeout=30, check=True,
            ).stdout.strip()

    def _board(self, paused):
        raids = [{"name": "r", "members": ["c"], "paused": paused, "lead": None}]
        return dict(_BOARD, raids=raids, projects=[{"name": "acme"}])

    def test_notice_form_lists_project_and_raid_scopes(self):
        out = self._rendered(self._board(False), "notices")
        self.assertIn("Create notice", out)
        self.assertIn("project:acme raid:r", out)
        self.assertIn("1h 8h 1d 3d", out)

    def test_raid_button_follows_the_paused_state(self):
        running = self._rendered(self._board(False), "raids")
        self.assertIn("Pause raid", running)
        self.assertNotIn("paused", running.replace("Pause raid", ""))
        paused = self._rendered(self._board(True), "raids")
        self.assertIn("Resume raid", paused)
        self.assertIn("paused", paused)

    def test_notice_from_unbound_session_shows_its_label_not_human(self):
        notice = {
            "id": 1, "party": None, "author": "unbound session", "scope": "guild", "text": "pipeline down",
            "issued_at": "now", "issued": "now", "expires_at": "later", "time_left": "1h left", "seen": False,
        }
        board = dict(self._board(False), notices=[notice])
        out = self._rendered(board, "notices")
        self.assertIn("unbound session", out)
        self.assertNotIn("human", out)

    def test_flagged_notice_shows_the_flagged_badge(self):
        notice = {
            "id": 1, "party": None, "author": "unbound session", "scope": "guild", "text": "orden del dev",
            "issued_at": "now", "issued": "now", "expires_at": "later", "time_left": "1h left", "seen": False,
            "flagged": True,
        }
        board = dict(self._board(False), notices=[notice])
        out = self._rendered(board, "notices")
        self.assertIn("flagged", out)

    def test_unflagged_notice_has_no_flagged_badge(self):
        notice = {
            "id": 1, "party": None, "author": "unbound session", "scope": "guild", "text": "pipeline down",
            "issued_at": "now", "issued": "now", "expires_at": "later", "time_left": "1h left", "seen": False,
            "flagged": False,
        }
        board = dict(self._board(False), notices=[notice])
        out = self._rendered(board, "notices")
        self.assertNotIn("flagged", out)


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebDispatchPauseBehaviorTests(unittest.TestCase):
    def _rendered(self, paused):
        dispatcher = {
            "in_flight": [], "failed": [], "deferred": [], "recent": [],
            "projects": [{"name": "acme", "rules": {"next_task": "on"}, "launches_last_hour": 0, "max_launches_per_hour": 3}],
            "paused": paused,
        }
        board = dict(_BOARD, dispatcher=dispatcher)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps(board))
            return subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(path), "all", "all", "dispatcher"],
                capture_output=True, text=True, timeout=30, check=True,
            ).stdout.strip()

    def test_running_dispatcher_shows_the_pause_form(self):
        out = self._rendered(None)
        self.assertIn("Pause dispatch", out)
        self.assertNotIn("Resume dispatch", out)

    def test_paused_dispatcher_shows_the_pill_and_resume_button(self):
        out = self._rendered({"reason": "deploy freeze", "paused_by": "human", "age": "5m"})
        self.assertIn("Resume dispatch", out)
        self.assertIn("deploy freeze", out)
        self.assertIn("paused", out)
        self.assertNotIn("Pause dispatch", out)
