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
    "generated_at": "now", "asks": [], "notices": [], "memory": [], "blocked": [], "merge_queues": [], "ready_for_you": [],
    "projects": [], "raids": [{"name": "r", "members": ["c"]}],
    "parties": [
        {
            "name": name, "raids": [], "quests": [], "prs": [], "claims": [], "state": "active", "generation": 1,
            "status": {"name": "idle", "label": "idle"}, "remaining": {"all_done": True}, "ctx": None,
            "resume_command": None, "caps": None, "drift": {"findings": [], "more": 0}, "leader_session_name": None, "waits": [],
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
            "human_state": "ready", "human_missing": [], "notes": [],
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
            "branch": "b", "checks_failing": 0, "checks_passing": 1, "checks_pending": 0, "labels": labels,
            "url": "https://example.test/1", "position": 1, "unblocks": 0,
            "state": "ready", "next_action": False, "action": "merge", "why": "ready", "reasons": [], "blockers": [],
            "waits": [], "gates": [], "human_state": "ready", "human_missing": [], "notes": [],
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

    def _human_text(self, **overrides):
        entry = {
            "ref": "o/r#1", "repo": "o/r", "number": 1, "party": "a", "task": "q/T1", "lifecycle": "ready",
            "branch": "b", "checks_failing": 0, "checks_passing": 0, "checks_pending": 0, "labels": [],
            "url": "https://example.test/1", "position": 1, "unblocks": 0, "blocked_external": None,
            "state": "ready", "next_action": False, "action": "merge", "why": "ready", "reasons": [], "blockers": [],
            "waits": [], "gates": [], "human_state": "ready", "human_missing": [], "notes": [],
        }
        entry.update(overrides)
        queue = {"head": None, "scope": "party:a", "synced_at": "now", "synced_label": "synced now", "main": [], "queue": [entry]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps(dict(_BOARD, merge_queues=[queue])))
            return subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(path), "all", "all", "merge-queues"],
                capture_output=True, text=True, timeout=30, check=True,
            ).stdout

    def test_ci_pending_entry_shows_pill_and_note(self):
        text = self._human_text(human_state="ready (CI pending)", notes=["CI label run-ci not on the PR"])
        self.assertIn("b ready (CI pending) no checks", text)
        self.assertIn("note: CI label run-ci not on the PR", text)

    def test_blocked_human_state_lists_missing_without_pill(self):
        text = self._human_text(human_state="blocked", human_missing=["1 comment after head"])
        self.assertIn("1 comment after head", text)
        self.assertNotIn("b ready no checks", text)
        self.assertNotIn("(CI pending)", text)

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
class WebMainRowBehaviorTests(unittest.TestCase):
    def _text(self, external):
        row = {"repo": "o/r", "source": "gh", "reason": "checks failing: lint", "external": external}
        queue = {"head": None, "scope": "party:a", "synced_at": "now", "synced_label": "synced now", "main": [row], "queue": []}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps(dict(_BOARD, merge_queues=[queue])))
            return subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(path), "all", "all", "merge-queues"],
                capture_output=True, text=True, timeout=30, check=True,
            ).stdout

    def test_red_main_row_says_fix_before_anything(self):
        text = self._text(None)
        self.assertIn("MAIN RED o/r", text)
        self.assertIn("fix before anything", text)

    def test_billing_blocked_main_row_says_rerun_once_fixed(self):
        text = self._text("billing")
        self.assertIn("MAIN BLOCKED (billing) o/r \u2192 re-run main once billing is fixed", text)
        self.assertNotIn("MAIN RED", text)


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
        raids = [{"name": "r", "members": ["c"], "paused": paused}]
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
class WebMemoryBehaviorTests(unittest.TestCase):
    def _rendered(self, items, party_filter):
        board = dict(_BOARD, memory=items)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps(board))
            result = subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(path), party_filter, "all", "memory"],
                capture_output=True, text=True, timeout=30, check=True,
            )
        return result.stdout.strip()

    def test_party_filter_keeps_only_that_party_memory(self):
        items = [
            {"id": "a/1", "party": "a", "text": "alpha note", "flagged": False},
            {"id": "c/1", "party": "c", "text": "charlie note", "flagged": False},
        ]
        out = self._rendered(items, "a")
        self.assertIn("alpha note", out)
        self.assertNotIn("charlie note", out)

    def test_flagged_item_shows_the_flagged_badge(self):
        items = [{"id": "a/1", "party": "a", "text": "orden del dev", "flagged": True}]
        out = self._rendered(items, "all")
        self.assertIn("flagged", out)

    def test_unflagged_item_has_no_flagged_badge(self):
        items = [{"id": "a/1", "party": "a", "text": "plain", "flagged": False}]
        out = self._rendered(items, "all")
        self.assertNotIn("flagged", out)


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebPartyHandoffBehaviorTests(unittest.TestCase):
    def _rendered(self, state, has_live_leader):
        parties = [
            dict(_BOARD["parties"][0], name="a", state=state, has_live_leader=has_live_leader)
        ]
        board = dict(_BOARD, parties=parties)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps(board))
            return subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(path), "all", "all", "parties"],
                capture_output=True, text=True, timeout=30, check=True,
            ).stdout.strip()

    def test_active_party_with_no_live_leader_shows_the_hand_off_button(self):
        self.assertIn("Hand off", self._rendered("active", False))

    def test_active_party_with_a_live_leader_has_no_hand_off_button(self):
        self.assertNotIn("Hand off", self._rendered("active", True))

    def test_non_active_party_has_no_hand_off_button(self):
        self.assertNotIn("Hand off", self._rendered("awaiting-leader", False))


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebPartyWaitsBehaviorTests(unittest.TestCase):
    def _rendered(self, waits):
        parties = [dict(_BOARD["parties"][0], name="a", waits=waits)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps(dict(_BOARD, parties=parties)))
            return subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(path), "all", "all", "parties"],
                capture_output=True, text=True, timeout=30, check=True,
            ).stdout.strip()

    def test_each_wait_renders_one_pill(self):
        waits = [
            {"kind": "checks-pending", "subject": "o/r#1", "label": "checks pending (2)"},
            {"kind": "ask-open", "subject": "ask #3", "label": "ask #3 open"},
        ]
        out = self._rendered(waits)
        self.assertIn("waits on:", out)
        self.assertIn("checks pending (2)", out)
        self.assertIn("ask #3 open", out)

    def test_party_without_waits_has_no_waits_line(self):
        self.assertNotIn("waits on:", self._rendered([]))


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebTaskMoveBehaviorTests(unittest.TestCase):
    def _rendered(self, task_state, move_targets):
        task = {
            "tid": "T01", "title": "First", "state": task_state, "summary": None,
            "blocked_reason": None, "card_url": None, "prs": [],
        }
        quest = {"slug": "src", "title": "Src", "move_targets": move_targets, "tasks": [task]}
        parties = [dict(_BOARD["parties"][0], name="a", quests=[quest])]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps(dict(_BOARD, parties=parties)))
            return subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(path), "all", "all", "parties"],
                capture_output=True, text=True, timeout=30, check=True,
            ).stdout.strip()

    def test_queued_task_lists_the_move_targets(self):
        out = self._rendered("queued", ["dst", "dst2"])
        self.assertIn("move to...", out)
        self.assertIn("dst2", out)

    def test_blocked_task_can_move(self):
        self.assertIn("move to...", self._rendered("blocked", ["dst"]))

    def test_active_task_has_no_move_control(self):
        self.assertNotIn("move to...", self._rendered("active", ["dst"]))

    def test_no_targets_means_no_move_control(self):
        self.assertNotIn("move to...", self._rendered("queued", []))


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebCtxBehaviorTests(unittest.TestCase):
    def _rendered(self, out_id):
        parties = [dict(party) for party in _BOARD["parties"]]
        parties[0]["ctx"] = {"pct": 42, "threshold": 75, "source": "compaction 85% − 10", "high": False}
        parties[1]["ctx"] = {"pct": 72, "threshold": 70, "source": "configured", "high": True}
        with tempfile.TemporaryDirectory() as tmp:
            board = Path(tmp) / "board.json"
            board.write_text(json.dumps(dict(_BOARD, parties=parties)))
            result = subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(board), "all", "all", out_id],
                capture_output=True, text=True, timeout=30, check=True,
            )
        return result.stdout.strip()

    def test_badge_shows_below_threshold_with_its_source(self):
        self.assertIn("context 42% / 75% (compaction 85% − 10)", self._rendered("parties"))

    def test_badge_without_a_derived_source_shows_only_the_values(self):
        out = self._rendered("parties")
        self.assertIn("context 72% / 70%", out)
        self.assertNotIn("(configured)", out)

    def test_only_high_contexts_count_as_context_high(self):
        self.assertIn("context high (1)", self._rendered("asks"))


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebCloseBlockersBehaviorTests(unittest.TestCase):
    def _parties_text(self, close_blockers):
        quest = {"slug": "q1", "title": "Quest", "move_targets": [], "tasks": [], "close_blockers": close_blockers}
        parties = [dict(_BOARD["parties"][0], quests=[quest])]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps(dict(_BOARD, parties=parties)))
            return subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(path), "all", "all", "parties"],
                capture_output=True, text=True, timeout=30, check=True,
            ).stdout

    def test_quest_with_blockers_shows_badge_and_both_lists(self):
        blockers = {"own": ["OWN1"], "foreign": [{"text": "FOR1", "party": "zed"}]}
        text = self._parties_text(blockers)
        self.assertIn("can't close: drift", text)
        self.assertIn("yours OWN1", text)
        self.assertIn("other parties FOR1 (party zed)", text)

    def test_quest_without_blockers_shows_no_badge(self):
        self.assertNotIn("can't close", self._parties_text(None))

    def test_empty_own_list_is_omitted(self):
        text = self._parties_text({"own": [], "foreign": [{"text": "FOR1", "party": "zed"}]})
        self.assertNotIn("yours", text)
        self.assertIn("other parties", text)


def _ready_item(ref, party, scopes, review_first, notes):
    return {
        "ref": ref, "title": "T " + ref, "url": "https://example.test/" + ref, "party": party, "scope": scopes[0], "scopes": scopes,
        "review_first": review_first, "checks": "1 passing", "notes": notes,
    }


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebReadyForYouBehaviorTests(unittest.TestCase):
    _ITEMS = [
        _ready_item("o/r#2", "a", ["party:a"], True, ["CI label x not on the PR"]),
        _ready_item("o/r#1", "c", ["raid:r", "raid:r2"], False, []),
        _ready_item("o/r#3", "a", ["party:a"], False, []),
    ]

    def _text(self, items, party_filter, raid_filter, mode):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "board.json"
            path.write_text(json.dumps(dict(_BOARD, ready_for_you=items, raids=[{"name": name, "members": ["c"]} for name in ("r", "r2", "other")])))
            return subprocess.run(
                ["node", str(_HARNESS), str(_APP_JS_PATH), str(path), party_filter, raid_filter, "ready-for-you", mode],
                capture_output=True, text=True, timeout=30, check=True,
            ).stdout.strip()

    def test_items_render_in_the_given_order(self):
        text = self._text(self._ITEMS, "all", "all", "text")
        self.assertEqual([text.index(ref) for ref in ("o/r#2", "o/r#1", "o/r#3")], sorted(text.index(ref) for ref in ("o/r#2", "o/r#1", "o/r#3")))
        self.assertIn("T o/r#1", text)

    def test_empty_state(self):
        self.assertEqual(self._text([], "all", "all", "text"), "ready for you nothing is ready for you")

    def test_review_first_pill_and_notes(self):
        text = self._text(self._ITEMS, "all", "all", "text")
        self.assertEqual(text.count("review first"), 1)
        self.assertIn("CI label x not on the PR", text)

    def test_party_filter_hides_other_parties(self):
        text = self._text(self._ITEMS, "a", "all", "text")
        self.assertIn("o/r#2", text)
        self.assertIn("o/r#3", text)
        self.assertNotIn("o/r#1", text)

    def test_raid_filter_keeps_the_raid_scope(self):
        text = self._text(self._ITEMS, "all", "r", "text")
        self.assertIn("o/r#1", text)
        self.assertNotIn("o/r#2", text)

    def test_raid_filter_keeps_an_item_on_its_second_raid(self):
        text = self._text(self._ITEMS, "all", "r2", "text")
        self.assertIn("o/r#1", text)
        self.assertNotIn("o/r#2", text)

    def test_raid_filter_hides_an_item_of_an_unrelated_raid(self):
        self.assertNotIn("o/r#1", self._text(self._ITEMS, "all", "other", "text"))

    def test_item_has_the_class_and_notes_in_their_own_block(self):
        tree = json.loads(self._text(self._ITEMS[:1], "all", "all", "tree"))
        item = tree["children"][1]["children"][0]
        self.assertEqual(item["className"], "ready-item")
        notes = item["children"][-1]
        self.assertEqual((notes["tag"], notes["className"]), ("div", "ready-notes"))
        self.assertIn("note: CI label x not on the PR", json.dumps(notes))
