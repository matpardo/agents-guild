import json
import re
import shutil
import unittest
from pathlib import Path

from guild import context, db, paths, timeutil
from guild.commands import board as board_commands
from tests import node_harness
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


_HARNESS_NAME = "web_drift_harness.js"


def _view_hash(party_filter, raid_filter):
    if party_filter != "all":
        return "#party/" + party_filter
    if raid_filter != "all":
        return "#raid/" + raid_filter
    return ""


def _render(board, party_filter, raid_filter, out_id, mode):
    return node_harness.request(_HARNESS_NAME, {
        "src": str(_APP_JS_PATH), "data": board, "hash": _view_hash(party_filter, raid_filter), "outId": out_id, "mode": mode,
    })


_MISSING = object()
_BOARD = {
    "generated_at": "now", "asks": [], "notices": [], "ideas": [], "adventurers": [], "health_jobs": [], "project_names": [], "memory": [], "blocked": [], "merge_queues": [], "ready_for_you": [],
    "projects": [], "quest_boards": [], "new_notice_count": 0, "raids": [{"name": "r", "members": ["c"]}],
    "parties": [
        {
            "name": name, "raids": [], "quests": [], "prs": [], "claims": [], "state": "active", "generation": 1,
            "reason": None, "from_adventurer": None, "started": "2026-10-24 10:00",
            "status": {"name": "idle", "label": "idle"}, "remaining": {"all_done": True}, "ctx": None,
            "resume_command": None, "caps": None, "drift": {"findings": [], "more": 0}, "leader_session_name": None, "waits": [], "ideas": [],
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
        result = _render(_BOARD, party_filter, raid_filter, "drift", "text")
        return result.strip()

    def test_no_filter_shows_every_finding(self):
        self.assertEqual(self._rendered("all", "all"), "drift p scope: x rule1 (3) FA FC FN rule2 (1) FC2")

    def test_party_filter_keeps_only_that_party(self):
        self.assertEqual(self._rendered("a", "all"), "drift p scope: x rule1 (1) FA")

    def test_raid_filter_keeps_member_findings_and_drops_empty_rules(self):
        self.assertEqual(self._rendered("all", "r"), "drift p scope: x rule1 (1) FC rule2 (1) FC2")

    def test_party_without_findings_shows_no_drift(self):
        board = dict(_BOARD, drift=[{"project": "p", "scope": "scope: x", "findings": {"rule1": [{"text": "FC", "party": "c"}]}}])
        out = _render(board, "a", "all", "drift", "text").strip()
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
        out = _render(board, "a", "all", "drift", "text").strip()
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
        return _render(dict(_BOARD, merge_queues=[queue]), "all", "all", "merge-queues", "text")

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
        return _render(dict(_BOARD, merge_queues=[queue]), "all", "all", "merge-queues", "text")

    def test_unseen_comments_offer_the_ack_button(self):
        text = self._human_text(unseen_comments=2, gates=["2 review comments since last read (guild pr ack o/r#1)"])
        self.assertIn("Mark 2 comments read", text)
        self.assertIn("gate: 2 review comments since last read", text)

    def test_single_unseen_comment_is_singular(self):
        self.assertIn("Mark 1 comment read", self._human_text(unseen_comments=1))

    def test_no_unseen_comments_hide_the_ack_button(self):
        self.assertNotIn("comments read", self._human_text(unseen_comments=0))

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

    def test_queue_entry_offers_relink_and_untrack(self):
        text = self._queue_text(None)
        self.assertIn("Relink", text)
        self.assertIn("Untrack", text)

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
        return _render(dict(_BOARD, merge_queues=[queue]), "all", "all", "merge-queues", "text")

    def test_red_main_row_says_fix_before_anything(self):
        text = self._text(None)
        self.assertIn("MAIN RED o/r", text)
        self.assertIn("fix before anything", text)

    def test_billing_blocked_main_row_says_rerun_once_fixed(self):
        text = self._text("billing")
        self.assertIn("MAIN BLOCKED (billing) o/r \u2192 re-run main once billing is fixed", text)
        self.assertNotIn("MAIN RED", text)


def _health_job(**overrides):
    job = {"project": "acme", "name": "red-main", "state": "due", "last_done": None, "every": "1d",
           "launch": "guild adventurer launch red-main"}
    return dict(job, **overrides)


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebHealthJobBehaviorTests(unittest.TestCase):
    def _text(self, jobs, party_filter="all"):
        return _render(dict(_BOARD, health_jobs=jobs), party_filter, "all", "health-jobs", "text")

    def test_due_job_shows_the_launch_command(self):
        out = self._text([_health_job()])
        for expected in ("red-main", "due", "acme", "guild adventurer launch red-main", "never"):
            self.assertIn(expected, out)

    def test_running_job_shows_running_without_launch_command(self):
        out = self._text([_health_job(state="running")])
        self.assertIn("running", out)
        self.assertNotIn("guild adventurer launch", out)

    def test_ok_job_is_hidden(self):
        self.assertEqual(self._text([_health_job(state="ok", last_done="2026-10-23T00:00:00+00:00")]), "")

    def test_jobs_survive_the_party_filter(self):
        self.assertIn("red-main", self._text([_health_job()], "a"))

    def test_there_is_no_launch_post_from_the_web(self):
        self.assertNotIn("/api/health", _APP_JS)


def _adventurer(**overrides):
    entry = {
        "id": 1, "project": "acme", "job": "fix typo", "task": "demo/T02", "state": "active", "pending": None,
        "live": False, "stopped_without_report": True, "prs": [], "reason": None, "started": "2026-10-24 10:00",
    }
    return dict(entry, **overrides)


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebAdventurerBehaviorTests(unittest.TestCase):
    def _text(self, adventurers, party_filter="all"):
        return _render(dict(_BOARD, adventurers=adventurers), party_filter, "all", "adventurers", "text")

    def test_active_stopped_adventurer_shows_job_state_and_the_flag(self):
        out = self._text([_adventurer()])
        for expected in ("adventurer 1 fix typo", "acme", "task demo/T02", "stopped", "stopped without report"):
            self.assertIn(expected, out)
        self.assertNotIn("Dismiss", out)

    def test_reason_and_start_time_show_only_when_present(self):
        out = self._text([_adventurer(reason="one PR job")])
        self.assertIn("reason: one PR job", out)
        self.assertIn("started 2026-10-24 10:00", out)
        self.assertNotIn("reason:", self._text([_adventurer()]))

    def test_party_card_shows_origin(self):
        party = dict(_BOARD["parties"][0], reason="grew to several PRs", from_adventurer=4)
        out = _render(dict(_BOARD, parties=[party]), "all", "all", "parties", "text")
        self.assertIn("started 2026-10-24 10:00", out)
        self.assertIn("from adventurer 4", out)
        self.assertIn("reason: grew to several PRs", out)
        plain = _render(_BOARD, "all", "all", "parties", "text")
        self.assertNotIn("from adventurer", plain)
        self.assertNotIn("reason:", plain)

    def test_live_adventurer_has_no_flag(self):
        out = self._text([_adventurer(live=True, stopped_without_report=False)])
        self.assertIn("live", out)
        self.assertNotIn("stopped without report", out)

    def test_done_adventurer_shows_pending_and_a_dismiss_button(self):
        out = self._text([_adventurer(state="done", pending="ping the owner", stopped_without_report=False)])
        self.assertIn("pending: ping the owner", out)
        self.assertIn("Dismiss", out)
        self.assertNotIn("stopped without report", out)

    def test_adventurer_pr_shows_under_the_adventurer_and_not_under_a_party(self):
        pr = {
            "repo": "o/r", "number": 7, "lifecycle": "draft", "what": "typo fix", "task": None, "card": "ABC-1",
            "card_url": None, "waits": "review", "branch": "fix/typo", "url": None, "base_branch": None,
            "needs_ask_answer": False, "needs_human_pr_review": False, "fixes_main": False, "fixes_flaky": False,
            "blocked_external": None, "ask_id": None, "review_reasons": [], "checks_failing": 0, "checks_passing": 0,
            "checks_pending": 0,
        }
        board = dict(_BOARD, adventurers=[_adventurer(prs=[pr])])
        adventurer_out = _render(board, "all", "all", "adventurers", "text")
        self.assertIn("typo fix", adventurer_out)
        parties_out = _render(board, "all", "all", "parties", "text")
        self.assertNotIn("typo fix", parties_out)
        self.assertNotIn("PRs outside active tasks", parties_out)

    def test_adventurers_survive_the_party_filter(self):
        self.assertIn("fix typo", self._text([_adventurer()], "a"))

    def test_dismiss_posts_through_send_post(self):
        self.assertIn('"/api/adventurers/" + adventurerId + "/dismiss"', _APP_JS)
        self.assertIn("sendPost(adventurerDismissUrl(adventurerId), {})", _APP_JS)

    def test_empty_section_renders_nothing(self):
        self.assertEqual(self._text([]).strip(), "")

    def test_party_card_shows_the_flag_only_when_set(self):
        parties = [dict(_BOARD["parties"][0], stopped_without_report=flag) for flag in (True, False)]
        parties[1]["name"] = "c"
        out = _render(dict(_BOARD, parties=parties), "all", "all", "parties", "text")
        self.assertEqual(out.count("stopped without report"), 1)


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebNoticeAndRaidBehaviorTests(unittest.TestCase):
    def _rendered(self, board, out_id):
        return _render(board, "all", "all", out_id, "text").strip()

    def _board(self, paused):
        raids = [{"name": "r", "members": ["c"], "paused": paused}]
        return dict(_BOARD, raids=raids, projects=[{"name": "acme"}])

    def test_notice_form_lists_project_and_raid_scopes(self):
        out = self._rendered(self._board(False), "notices")
        self.assertIn("Create notice", out)
        self.assertIn("project:acme raid:r", out)
        self.assertIn("1h 8h 1d 3d", out)

    def _idea(self, **overrides):
        idea = {
            "id": 1, "title": "Dark mode", "description": "night owls", "requester": "ana",
            "deadline": "2000-01-01", "project": "acme", "dates": "created 2026-10-01 10:00", "overdue": True,
            "parties": [],
        }
        return dict(idea, **overrides)

    def test_ideas_render_with_meta_and_overdue_mark(self):
        board = dict(self._board(False), ideas=[self._idea()])
        out = self._rendered(board, "ideas")
        for expected in ("#1 Dark mode", "night owls", "from ana", "due 2000-01-01 (overdue)", "Edit", "Delete", "Add idea"):
            self.assertIn(expected, out)

    def test_idea_shows_linked_parties_with_unlink_and_link_choices(self):
        idea = self._idea(parties=[{"name": "a", "state": "active"}, {"name": "old", "state": "closed"}])
        board = dict(self._board(False), ideas=[idea])
        out = self._rendered(board, "ideas")
        for expected in ("worked by:", "a", "old (closed)", "Unlink", "Link"):
            self.assertIn(expected, out)
        tree = json.loads(_render(board, "all", "all", "ideas", "tree"))
        selects = []

        def walk(node):
            if node["tag"] == "select":
                selects.append([child["text"] for child in node["children"]])
            for child in node["children"]:
                walk(child)

        walk(tree)
        self.assertIn(["c"], selects)

    def test_idea_without_parties_has_no_worked_by(self):
        out = self._rendered(dict(self._board(False), ideas=[self._idea()]), "ideas")
        self.assertNotIn("worked by", out)
        self.assertIn("not linked yet", out)
        self.assertIn("created 2026-10-01 10:00", out)
        self.assertIn("Link", out)

    def test_linked_idea_is_not_marked_unlinked(self):
        idea = self._idea(parties=[{"name": "a", "state": "active"}])
        out = self._rendered(dict(self._board(False), ideas=[idea]), "ideas")
        self.assertNotIn("not linked yet", out)

    def test_idea_description_view_keeps_line_breaks_class(self):
        board = dict(self._board(False), ideas=[self._idea()])
        nodes = self._tree_nodes(_render(board, "all", "all", "ideas", "tree"))
        views = [n for n in nodes if n["tag"] == "p" and "idea-description" in n["className"]]
        self.assertEqual([n["text"] for n in views], ["night owls"])

    def test_idea_description_input_is_a_textarea(self):
        area = [n for n in self._idea_form_inputs() if "idea-description" in n["className"]][0]
        self.assertEqual((area["tag"], area["placeholder"]), ("textarea", "description"))

    def test_party_card_lists_its_ideas(self):
        party = dict(_BOARD["parties"][0], ideas=[{"id": 1, "title": "Dark mode"}])
        out = self._rendered(dict(_BOARD, parties=[party]), "parties")
        self.assertIn("ideas: #1 Dark mode", out)

    def test_idea_not_overdue_has_no_overdue_mark(self):
        board = dict(self._board(False), ideas=[self._idea(overdue=False, deadline="2099-01-01")])
        out = self._rendered(board, "ideas")
        self.assertIn("due 2099-01-01", out)
        self.assertNotIn("overdue", out)

    def _tree_nodes(self, out):
        found = []

        def walk(node):
            found.append(node)
            for child in node["children"]:
                walk(child)

        walk(json.loads(out))
        return found

    def _idea_form_inputs(self):
        board = dict(self._board(False), ideas=[], project_names=["acme", "zeta"])
        return self._tree_nodes(_render(board, "all", "all", "ideas", "tree"))

    def test_idea_deadline_input_is_a_text_field_asking_for_iso_dates(self):
        deadline = [n for n in self._idea_form_inputs() if "idea-deadline" in n["className"]][0]
        self.assertEqual((deadline["type"], deadline["placeholder"]), ("text", "deadline YYYY-MM-DD"))

    def test_idea_project_select_lists_every_registered_project_and_names_the_empty_choice(self):
        options = [n["text"] for n in self._idea_form_inputs() if n["tag"] == "option"]
        self.assertEqual(options, ["no project", "acme", "zeta"])

    def test_ideas_survive_the_party_filter(self):
        out = _render(dict(self._board(False), ideas=[self._idea()]), "a", "all", "ideas", "text")
        self.assertIn("Dark mode", out)

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
        result = _render(board, party_filter, "all", "memory", "text")
        return result.strip()

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
        return _render(board, "all", "all", "parties", "text").strip()

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
        return _render(dict(_BOARD, parties=parties), "all", "all", "parties", "text").strip()

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
        return _render(dict(_BOARD, parties=parties), "all", "all", "parties", "text").strip()

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
        result = _render(dict(_BOARD, parties=parties), "all", "all", out_id, "text")
        return result.strip()

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
        return _render(dict(_BOARD, parties=parties), "all", "all", "parties", "text")

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
        return _render(dict(_BOARD, ready_for_you=items, raids=[{"name": name, "members": ["c"]} for name in ("r", "r2", "other")]), party_filter, raid_filter, "ready-for-you", mode).strip()

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


_QUEST_BOARD = {
    "open_quests": [{
        "slug": "pre", "epic": "demo", "title": "Pre work",
        "tasks": [{"tid": "T01", "title": "First", "adventurer": None}, {"tid": "T02", "title": "Second", "adventurer": 7}],
    }],
    "free_tasks": [{"epic": "demo", "tasks": [{"tid": "T03", "title": "Third"}, {"tid": "T04", "title": "Fourth"}]}],
    "parties": ["a", "c"], "name": "acme",
}


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebQuestBoardBehaviorTests(unittest.TestCase):
    def _text(self, quest_board, out_id="quest-board"):
        board = dict(_BOARD, quest_boards=[quest_board])
        return _render(board, "all", "all", out_id, "text")

    def test_lists_open_quest_tasks_and_marks_the_held_one(self):
        out = self._text(_QUEST_BOARD)
        for expected in ("quest board", "acme", "pre", "Pre work", "T01 First", "T02 Second (held by adventurer 7)", "Assign"):
            self.assertIn(expected, out)

    def test_assign_select_offers_the_active_parties(self):
        board = dict(_BOARD, quest_boards=[_QUEST_BOARD])
        tree = json.loads(_render(board, "all", "all", "quest-board", "tree"))
        selects = []

        def walk(node):
            if node["tag"] == "select":
                selects.append(node)
            for child in node["children"]:
                walk(child)

        walk(tree)
        self.assertEqual([option["text"] for option in selects[0]["children"]], ["a", "c"])

    def test_free_tasks_get_checkboxes_and_a_create_button(self):
        out = self._text(_QUEST_BOARD)
        for expected in ("free tasks", "T03 Third", "T04 Fourth", "Create open quest"):
            self.assertIn(expected, out)

    def test_project_with_no_parties_still_renders_with_a_disabled_assign(self):
        out = self._text(dict(_QUEST_BOARD, parties=[]), "quest-board")
        self.assertIn("Assign", out)
        self.assertIn("Create open quest", out)

    def test_empty_board_shows_no_forms(self):
        out = self._text({"name": "acme", "open_quests": [], "free_tasks": [], "parties": []})
        self.assertNotIn("Assign", out)
        self.assertNotIn("Create open quest", out)

    def test_party_quest_shows_release_only_when_releasable(self):
        def parties(releasable):
            quest = {"slug": "q", "title": "Q", "tasks": [], "close_blockers": None, "move_targets": [], "releasable": releasable}
            return [dict(_BOARD["parties"][0], quests=[quest])]

        shown = _render(dict(_BOARD, parties=parties(True)), "all", "all", "parties", "text")
        hidden = _render(dict(_BOARD, parties=parties(False)), "all", "all", "parties", "text")
        self.assertIn("Release", shown)
        self.assertNotIn("Release", hidden)

    def test_writes_go_through_send_post(self):
        for expected in ('"/api/quests/create-open"', '"/api/quests/" + quest.slug + "/take"', '"/api/quests/" + quest.slug + "/release"'):
            self.assertIn(expected, _APP_JS)
