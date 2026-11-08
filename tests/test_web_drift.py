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
            conn,
            None,
            None,
            timeutil.utcnow(),
            None,
            paths.claude_sessions_dir(),
            paths.projects_config_dir(),
            paths.state_dir(),
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
    return _render_at(board, _view_hash(party_filter, raid_filter), out_id, mode)


def _render_at(board, view_hash, out_id, mode):
    return node_harness.request(
        _HARNESS_NAME,
        {
            "src": str(_APP_JS_PATH),
            "data": board,
            "hash": view_hash,
            "outId": out_id,
            "mode": mode,
        },
    )


def _project(name):
    return {
        "name": name,
        "max_open_prs": None,
        "open_prs": 0,
        "wait": None,
        "hot_files": [],
        "finding_classes": [],
        "freshness": {},
    }


_MISSING = object()
_BOARD = {
    "generated_at": "now",
    "asks": [],
    "notices": [],
    "ideas": [],
    "adventurers": [],
    "health_jobs": [],
    "solo_players": [],
    "solo_channel": [],
    "solo_pending": [],
    "project_names": [],
    "bases": [],
    "memory": [],
    "blocked": [],
    "merge_queues": [],
    "ready_for_you": [],
    "projects": [],
    "quest_boards": [],
    "realm": None,
    "new_notice_count": 0,
    "raids": [{"name": "r", "members": ["c"]}],
    "parties": [
        {
            "name": name,
            "raids": [],
            "quests": [],
            "prs": [],
            "claims": [],
            "state": "active",
            "generation": 1,
            "reason": None,
            "parked": None,
            "from_adventurer": None,
            "dates": "created 2026-10-24 10:00",
            "status": {"name": "idle", "label": "idle"},
            "remaining": {"all_done": True, "quests": [], "active": 0, "blocked": 0, "queued": 0},
            "ctx": None,
            "resume_command": None,
            "caps": None,
            "drift": {"findings": [], "more": 0},
            "leader_session_name": None,
            "waits": [],
            "ideas": [],
            "followups": [],
            "daily_tasks": [],
            "blocked_groups": [],
        }
        for name in ("a", "c")
    ],
    "drift": [
        {
            "project": "p",
            "scope": "scope: x",
            "findings": {
                "rule1": [{"text": "FA", "party": "a"}, {"text": "FC", "party": "c"}, {"text": "FN", "party": None}],
                "rule2": [{"text": "FC2", "party": "c"}],
            },
        }
    ],
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
        board = dict(
            _BOARD, drift=[{"project": "p", "scope": "scope: x", "findings": {"rule1": [{"text": "FC", "party": "c"}]}}]
        )
        out = _render(board, "a", "all", "drift", "text").strip()
        self.assertEqual(out, "drift p scope: x no drift")

    def test_party_filter_renders_a_board_with_a_merge_queue(self):
        entry = {
            "ref": "o/r#1",
            "repo": "o/r",
            "number": 1,
            "party": "a",
            "task": "q/T1",
            "lifecycle": "ready",
            "branch": "b",
            "checks_failing": 0,
            "checks_passing": 1,
            "checks_pending": 0,
            "labels": [],
            "url": "https://example.test/1",
            "position": 1,
            "unblocks": 0,
            "state": "ready",
            "next_action": False,
            "action": "merge",
            "why": "ready",
            "reasons": [],
            "blockers": [],
            "waits": [],
            "gates": [],
            "human_state": "ready",
            "human_missing": [],
            "notes": [],
        }
        queue = {
            "head": None,
            "scope": "party:a",
            "synced_at": "now",
            "synced_label": "synced now",
            "main": [],
            "queue": [entry],
        }
        board = dict(_BOARD, merge_queues=[queue])
        out = _render(board, "a", "all", "drift", "text").strip()
        self.assertEqual(out, "drift p scope: x rule1 (1) FA")


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebQueueBlockBehaviorTests(unittest.TestCase):
    def _queue_text(self, blocked_external):
        labels = [] if blocked_external in (None, _MISSING) else ["blocked-external"]
        entry = {
            "ref": "o/r#1",
            "repo": "o/r",
            "number": 1,
            "party": "a",
            "task": "q/T1",
            "lifecycle": "ready",
            "branch": "b",
            "checks_failing": 0,
            "checks_passing": 1,
            "checks_pending": 0,
            "labels": labels,
            "url": "https://example.test/1",
            "position": 1,
            "unblocks": 0,
            "state": "ready",
            "next_action": False,
            "action": "merge",
            "why": "ready",
            "reasons": [],
            "blockers": [],
            "waits": [],
            "gates": [],
            "human_state": "ready",
            "human_missing": [],
            "notes": [],
        }
        if blocked_external is not _MISSING:
            entry["blocked_external"] = blocked_external
        queue = {
            "head": None,
            "scope": "party:a",
            "synced_at": "now",
            "synced_label": "synced now",
            "main": [],
            "queue": [entry],
        }
        return _render(dict(_BOARD, merge_queues=[queue]), "all", "all", "merge-queues", "text")

    def _human_text(self, **overrides):
        entry = {
            "ref": "o/r#1",
            "repo": "o/r",
            "number": 1,
            "party": "a",
            "task": "q/T1",
            "lifecycle": "ready",
            "branch": "b",
            "checks_failing": 0,
            "checks_passing": 0,
            "checks_pending": 0,
            "labels": [],
            "url": "https://example.test/1",
            "position": 1,
            "unblocks": 0,
            "blocked_external": None,
            "state": "ready",
            "next_action": False,
            "action": "merge",
            "why": "ready",
            "reasons": [],
            "blockers": [],
            "waits": [],
            "gates": [],
            "human_state": "ready",
            "human_missing": [],
            "notes": [],
        }
        entry.update(overrides)
        queue = {
            "head": None,
            "scope": "party:a",
            "synced_at": "now",
            "synced_label": "synced now",
            "main": [],
            "queue": [entry],
        }
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
        queue = {
            "head": None,
            "scope": "party:a",
            "synced_at": "now",
            "synced_label": "synced now",
            "main": [row],
            "queue": [],
        }
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
    job = {
        "project": "acme",
        "name": "red-main",
        "state": "due",
        "last_done": None,
        "every": "1d",
        "launch": "guild adventurer launch red-main",
    }
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


def _solo_player(**overrides):
    player = {
        "project": "acme",
        "repo": "acme/app",
        "job": "red-main",
        "class": "cleric",
        "name": "mender",
        "health_job": "red-main-acme-app",
        "trigger": "main red: checks failing: lint",
        "schedule": "main-red",
        "state": "due",
        "last_done": None,
        "last_pending": None,
        "launch": "guild solo launch acme/app red-main",
        "waits_on": [],
        "stalled_adventurer": None,
        "retry_at": None,
        "runs": [],
        "to_merge": [],
    }
    return dict(player, **overrides)


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebSoloPlayerBehaviorTests(unittest.TestCase):
    def _text(self, players, party_filter="all"):
        return _render(dict(_BOARD, solo_players=players), party_filter, "all", "solo-players", "text")

    def test_due_player_shows_class_trigger_and_launch_command(self):
        out = self._text([_solo_player()])
        for expected in ("mender", "cleric", "acme/app", "due", "main red: checks failing: lint", "never", "none"):
            self.assertIn(expected, out)
        self.assertIn("guild solo launch acme/app red-main", out)

    def test_player_shows_its_schedule(self):
        out = self._text([_solo_player(schedule="every 7d", trigger=None, state="idle")])
        self.assertIn("on every 7d", out)

    def test_idle_player_shows_no_trigger_and_launch_command(self):
        out = self._text([_solo_player(trigger=None, state="idle")])
        self.assertIn("no trigger", out)
        self.assertIn("guild solo launch acme/app red-main", out)

    def test_running_and_cooling_players_hide_the_launch_command(self):
        for state in ("running", "cooling"):
            out = self._text(
                [_solo_player(state=state, last_done="2026-11-01T00:00:00+00:00", last_pending="none left")]
            )
            self.assertIn(state, out)
            self.assertIn("none left", out)
            self.assertNotIn("guild solo launch", out)

    def test_fixing_player_shows_what_it_waits_on_without_launch_command(self):
        out = self._text([_solo_player(state="fixing", waits_on=["acme/app#12"])])
        self.assertIn("fixing", out)
        self.assertIn("fixing: waits on acme/app#12", out)
        self.assertNotIn("guild solo launch", out)

    def test_stalled_player_shows_the_dismiss_hint_without_launch_command(self):
        out = self._text([_solo_player(state="stalled", stalled_adventurer=7)])
        self.assertIn("stalled: session gone, run guild adventurer dismiss 7", out)
        self.assertNotIn("guild solo launch", out)

    def test_to_merge_lists_each_ready_pr_with_its_title(self):
        entries = [
            {"ref": "acme/app#1", "repo": "acme/app", "title": "Bump x", "url": "https://github.com/acme/app/pull/1"},
            {"ref": "acme/app#2", "repo": "acme/app", "title": "Bump y", "url": "https://github.com/acme/app/pull/2"},
        ]
        out = self._text([_solo_player(job="dependabot", to_merge=entries)])
        for expected in ("to merge", "acme/app#1", "Bump x", "acme/app#2", "Bump y"):
            self.assertIn(expected, out)

    def test_to_merge_is_absent_when_the_list_is_empty(self):
        self.assertNotIn("to merge", self._text([_solo_player(job="dependabot")]))

    def test_paused_player_shows_state_and_the_resume_command(self):
        out = self._text([_solo_player(state="paused", launch="guild solo resume acme/app red-main")])
        self.assertIn("paused", out)
        self.assertIn("guild solo resume acme/app red-main", out)

    def test_backing_off_player_shows_the_retry_time(self):
        out = self._text([_solo_player(state="cooling", retry_at="2026-11-02T10:00:00+00:00")])
        self.assertRegex(out, r"cooling: same trigger, retry after \d{4}-\d{2}-\d{2} \d{2}:\d{2}")
        self.assertNotIn("guild solo launch", out)

    def _channel_text(self, channel, players):
        return _render(dict(_BOARD, solo_players=players, solo_channel=channel), "all", "all", "solo-players", "text")

    def test_channel_feed_shows_time_name_class_and_text(self):
        message = {
            "ts": "2026-11-02T09:30:00+00:00",
            "name": "mender",
            "class": "cleric",
            "project": "acme",
            "text": "fix PR ready",
        }
        out = self._channel_text([message], [_solo_player()])
        for expected in ("mender", "cleric", "fix PR ready"):
            self.assertIn(expected, out)

    def test_empty_channel_shows_heading_and_placeholder(self):
        out = self._channel_text([], [_solo_player()])
        self.assertIn("channel", out)
        self.assertIn("no messages yet", out)

    def test_filled_channel_has_no_placeholder(self):
        message = {"ts": "2026-11-02T09:30:00+00:00", "name": "mender", "class": "", "project": "acme", "text": "hi"}
        self.assertNotIn("no messages yet", self._channel_text([message], [_solo_player()]))

    def test_dates_use_the_short_local_format(self):
        message = {"ts": "2026-11-02T09:30:00+00:00", "name": "mender", "class": "", "project": "acme", "text": "hi"}
        run = {
            "started_at": "2026-11-02T08:00:00+00:00",
            "done_at": None,
            "state": "running",
            "duration": None,
            "pending": None,
            "prs": [],
        }
        player = _solo_player(
            last_done="2026-11-01T10:00:00+00:00", retry_at="2026-11-02T10:00:00+00:00", state="cooling", runs=[run]
        )
        out = self._channel_text([message], [player])
        self.assertNotIn("+00:00", out)
        self.assertNotRegex(out, r"\d{4}-\d{2}-\d{2}T")
        self.assertGreaterEqual(len(re.findall(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", out)), 4)

    def test_channel_text_stays_literal(self):
        message = {
            "ts": "t",
            "name": "mender",
            "class": "cleric",
            "project": "acme",
            "text": "<img src=x onerror=alert(1)>",
        }
        board = dict(_BOARD, solo_players=[_solo_player()], solo_channel=[message])
        tree = _render(board, "all", "all", "solo-players", "tree")
        self.assertIn("<img src=x onerror=alert(1)>", tree)
        self.assertNotIn('"tag":"img"', tree)

    def test_channel_has_no_input(self):
        message = {"ts": "t", "name": "mender", "class": "cleric", "project": "acme", "text": "hi"}
        board = dict(_BOARD, solo_players=[_solo_player()], solo_channel=[message])
        tree = _render(board, "all", "all", "solo-players", "tree")
        self.assertNotIn('"tag":"input"', tree)
        self.assertNotIn('"tag":"textarea"', tree)

    def test_runs_render_in_a_details_with_literal_pending(self):
        run = {
            "started_at": "2026-11-02T08:00:00+00:00",
            "done_at": "2026-11-02T08:20:00+00:00",
            "state": "done",
            "duration": 1200,
            "pending": "<img src=x onerror=alert(1)>",
            "prs": [{"ref": "acme/app#7", "lifecycle": "converging"}, {"ref": "acme/app#9", "lifecycle": "ready"}],
        }
        running = {
            "started_at": "2026-11-02T09:00:00+00:00",
            "done_at": None,
            "state": "running",
            "duration": None,
            "pending": None,
            "prs": [],
        }
        board = dict(_BOARD, solo_players=[_solo_player(runs=[running, run])])
        tree = _render(board, "all", "all", "solo-players", "tree")
        self.assertIn('"tag":"details"', tree)
        self.assertIn("<img src=x onerror=alert(1)>", tree)
        self.assertNotIn('"tag":"img"', tree)
        text = _render(board, "all", "all", "solo-players", "text")
        for expected in ("runs", "running", "done", "20m", "PRs: acme/app#7 converging, acme/app#9 ready"):
            self.assertIn(expected, text)

    def test_player_without_runs_has_no_details(self):
        tree = _render(dict(_BOARD, solo_players=[_solo_player()]), "all", "all", "solo-players", "tree")
        self.assertNotIn('"tag":"details"', tree)

    def test_no_players_render_nothing(self):
        self.assertEqual(self._text([]), "")

    def test_players_survive_the_party_filter(self):
        self.assertIn("mender", self._text([_solo_player()], "a"))


def _walk_tree(node):
    nodes = [node]
    for child in node["children"]:
        nodes.extend(_walk_tree(child))
    return nodes


def _two_project_board():
    players = [
        _solo_player(project="acme", name="mender"),
        _solo_player(project="acme", name="dep", job="dependabot"),
        _solo_player(project="zeta", name="zed", repo="zeta/app"),
    ]
    channel = [
        {"ts": "t", "name": "zed", "class": "", "text": "zeta said", "project": "zeta"},
        {"ts": "t", "name": "mender", "class": "", "text": "acme said", "project": "acme"},
    ]
    return dict(_BOARD, solo_players=players, solo_channel=channel, project_names=["acme", "idle", "zeta"])


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebSoloByProjectTests(unittest.TestCase):
    def _text(self, view_hash):
        return _render_at(_two_project_board(), view_hash, "solo-players", "text")

    def test_bare_view_selects_the_first_project_alphabetically(self):
        out = self._text("#solo-players")
        self.assertIn("acme said", out)
        self.assertIn("mender", out)
        self.assertNotIn("zeta said", out)
        self.assertNotIn("zed", out)

    def _tabs(self, view_hash, board):
        tree = json.loads(_render_at(board, view_hash, "solo-players", "tree"))
        nodes = _walk_tree(tree)
        bar = [node for node in nodes if node["attrs"].get("role") == "tablist"]
        self.assertEqual(len(bar), 1)
        return [(tab["text"], tab["attrs"]["aria-selected"]) for tab in bar[0]["children"]]

    def test_one_tab_per_project_with_the_current_selected(self):
        self.assertEqual(self._tabs("#solo-players/zeta", _two_project_board()), [("acme", "false"), ("zeta", "true")])

    def test_bare_view_marks_the_first_tab_selected(self):
        self.assertEqual(self._tabs("#solo-players", _two_project_board()), [("acme", "true"), ("zeta", "false")])

    def test_tab_bar_shows_with_a_single_project(self):
        board = dict(_two_project_board(), solo_players=[_solo_player()])
        self.assertEqual(self._tabs("#solo-players", board), [("acme", "true")])

    def test_clicking_a_tab_sets_the_hash(self):
        request = {
            "src": str(_APP_JS_PATH),
            "data": _two_project_board(),
            "hash": "#solo-players",
            "outId": "solo-players",
            "mode": "hash",
            "click": "zeta",
        }
        self.assertEqual(node_harness.request(_HARNESS_NAME, request), "#solo-players/zeta")

    def test_channel_comes_after_the_players(self):
        out = self._text("#solo-players/acme")
        self.assertLess(out.index("mender"), out.index("channel"))
        self.assertLess(out.index("channel"), out.index("acme said"))

    def test_project_view_renders_only_that_project(self):
        out = self._text("#solo-players/zeta")
        self.assertIn("zeta said", out)
        self.assertIn("zed", out)
        self.assertNotIn("acme said", out)
        self.assertNotIn("mender", out)

    def test_project_without_messages_shows_the_placeholder(self):
        board = _two_project_board()
        board["solo_channel"] = [message for message in board["solo_channel"] if message["project"] == "zeta"]
        out = _render_at(board, "#solo-players/acme", "solo-players", "text")
        self.assertIn("no messages yet", out)
        self.assertNotIn("zeta said", out)

    def _solo_menu(self, view_hash):
        tree = json.loads(_render_at(_two_project_board(), view_hash, "sidebar", "tree"))
        menu = [node for node in _walk_tree(tree) if node["tag"] == "details"]
        self.assertEqual(len(menu), 1)
        return menu[0]

    def test_solo_menu_is_collapsed_by_default(self):
        menu = self._solo_menu("#solo-players")
        self.assertFalse(menu["open"])
        self.assertEqual(menu["children"][0]["tag"], "summary")
        self.assertEqual(menu["children"][0]["children"][0]["text"], "solo players (3)")

    def test_solo_menu_opens_when_the_hash_names_a_project(self):
        self.assertTrue(self._solo_menu("#solo-players/zeta")["open"])

    def _menu_open_after(self, steps):
        request = {
            "src": str(_APP_JS_PATH),
            "data": _two_project_board(),
            "hash": "#solo-players/acme",
            "outId": "sidebar",
            "mode": "tree",
            "steps": steps,
        }
        tree = json.loads(node_harness.request(_HARNESS_NAME, request))
        return [node for node in _walk_tree(tree) if node["tag"] == "details"][0]["open"]

    def test_menu_opens_on_the_first_render_of_a_project_hash(self):
        self.assertTrue(self._menu_open_after([]))

    def test_closed_menu_stays_closed_on_a_poll_with_the_same_hash(self):
        self.assertFalse(self._menu_open_after(["close-details", "poll"]))

    def test_navigating_to_another_project_reopens_the_menu(self):
        self.assertTrue(self._menu_open_after(["close-details", "poll", "#solo-players/zeta"]))

    def test_sidebar_lists_only_projects_with_players(self):
        tree = _render_at(_two_project_board(), "#solo-players", "sidebar", "tree")
        text = _render_at(_two_project_board(), "#solo-players", "sidebar", "text")
        self.assertIn("solo players (3)", text)
        self.assertIn("acme (2)", text)
        self.assertIn("zeta (1)", text)
        self.assertNotIn("idle (", text)
        self.assertIn(
            '"tag":"a","className":"","type":"","value":"all","placeholder":"","title":"","text":"acme (2)"', tree
        )

    def test_project_view_shows_the_solo_players_section(self):
        hidden = json.loads(_render_at(_two_project_board(), "#solo-players/acme", "x", "hidden"))
        self.assertNotIn("solo-players", hidden)
        self.assertIn("adventurers", hidden)

    def test_project_text_stays_literal(self):
        board = _two_project_board()
        board["solo_channel"][0]["text"] = "<img src=x onerror=alert(1)>"
        tree = _render_at(board, "#solo-players/zeta", "solo-players", "tree")
        self.assertIn("<img src=x onerror=alert(1)>", tree)
        self.assertNotIn('"tag":"img"', tree)


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebBasesBehaviorTests(unittest.TestCase):
    def _tree(self, bases):
        return json.loads(_render(dict(_BOARD, bases=bases), "all", "all", "bases", "tree"))

    def _pills(self, bases):
        tree = self._tree(bases)
        return [(line["children"][0]["className"], line["children"][0]["text"]) for line in tree["children"][1:]]

    def test_behind_repo_shows_a_warning_pill_and_up_to_date_an_ok_pill(self):
        bases = [
            {
                "repo": "o/a",
                "base": "main",
                "behind": 2,
                "ahead": 0,
                "warn": True,
                "text": "o/a main: 2 behind (never fetched)",
            },
            {
                "repo": "o/b",
                "base": "main",
                "behind": 0,
                "ahead": 0,
                "warn": False,
                "text": "o/b main: up to date (fetched 1m ago)",
            },
        ]
        self.assertEqual(
            self._pills(bases),
            [
                ("pill res-warn", "o/a main: 2 behind (never fetched)"),
                ("pill res-ok", "o/b main: up to date (fetched 1m ago)"),
            ],
        )

    def test_each_base_has_a_pause_or_resume_button(self):
        bases = [
            {
                "repo": "o/a",
                "base": "main",
                "behind": 0,
                "ahead": 0,
                "paused": False,
                "warn": False,
                "text": "o/a main: up to date",
            },
            {
                "repo": "o/b",
                "base": None,
                "behind": None,
                "ahead": None,
                "paused": True,
                "warn": False,
                "text": "o/b: paused",
            },
        ]
        lines = self._tree(bases)["children"][1:]
        self.assertEqual(
            [(line["children"][0]["className"], line["children"][1]["text"]) for line in lines],
            [("pill res-ok", "pause"), ("pill lifecycle-blocked-external", "resume")],
        )

    def test_no_bases_renders_nothing(self):
        self.assertEqual(self._tree([])["children"], [])


def _ask(**overrides):
    entry = {
        "id": 3,
        "party": "a",
        "question": "Ship it?",
        "context": "x",
        "options": [],
        "recommend": None,
        "refs": ["card:ABC-1"],
        "blocked": 0,
        "total_refs": 1,
        "created_at": "2026-10-24T10:00:00+00:00",
        "state": "open",
        "answer": None,
        "answered_at": None,
        "dates": "created 2026-10-24 10:00",
    }
    return dict(entry, **overrides)


def _adventurer(**overrides):
    entry = {
        "id": 1,
        "project": "acme",
        "job": "fix typo",
        "task": "demo/T02",
        "state": "active",
        "pending": None,
        "live": False,
        "stopped_without_report": True,
        "prs": [],
        "ideas": [],
        "reason": None,
        "dates": "created 2026-10-24 10:00",
    }
    return dict(entry, **overrides)


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebAskDatesBehaviorTests(unittest.TestCase):
    def _text(self, ask):
        return _render(dict(_BOARD, asks=[ask]), "all", "all", "asks", "text")

    def test_open_ask_shows_dates(self):
        self.assertIn("created 2026-10-24 10:00", self._text(_ask()))

    def test_null_dates_are_hidden(self):
        self.assertNotIn("created", self._text(_ask(dates=None)))


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebAdventurerBehaviorTests(unittest.TestCase):
    def _text(self, adventurers, party_filter="all"):
        return _render(dict(_BOARD, adventurers=adventurers), party_filter, "all", "adventurers", "text")

    def test_active_stopped_adventurer_shows_job_state_and_the_flag(self):
        out = self._text([_adventurer()])
        for expected in ("adventurer 1 fix typo", "acme", "task demo/T02", "stopped", "stopped without report"):
            self.assertIn(expected, out)
        self.assertNotIn("Dismiss", out)

    def test_adventurer_card_lists_its_ideas(self):
        out = self._text([_adventurer(ideas=[{"id": 1, "title": "Dark mode"}])])
        self.assertIn("ideas: #1 Dark mode", out)

    def test_reason_and_start_time_show_only_when_present(self):
        out = self._text([_adventurer(reason="one PR job")])
        self.assertIn("reason: one PR job", out)
        self.assertIn("created 2026-10-24 10:00", out)
        self.assertNotIn("reason:", self._text([_adventurer()]))

    def test_done_adventurer_shows_both_dates(self):
        out = self._text([_adventurer(state="done", dates="created 2026-10-24 10:00 · updated 2026-10-24 11:00")])
        self.assertIn("created 2026-10-24 10:00 · updated 2026-10-24 11:00", out)

    def test_party_card_shows_origin(self):
        party = dict(_BOARD["parties"][0], reason="grew to several PRs", from_adventurer=4)
        out = _render(dict(_BOARD, parties=[party]), "all", "all", "parties", "text")
        self.assertIn("created 2026-10-24 10:00", out)
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
            "repo": "o/r",
            "number": 7,
            "lifecycle": "draft",
            "what": "typo fix",
            "task": None,
            "card": "ABC-1",
            "card_url": None,
            "waits": "review",
            "branch": "fix/typo",
            "url": None,
            "base_branch": None,
            "needs_ask_answer": False,
            "needs_human_pr_review": False,
            "fixes_main": False,
            "fixes_flaky": False,
            "blocked_external": None,
            "ask_id": None,
            "review_reasons": [],
            "checks_failing": 0,
            "checks_passing": 0,
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
        return dict(_BOARD, raids=raids, projects=[_project("acme")])

    def test_notice_form_lists_project_and_raid_scopes(self):
        out = self._rendered(self._board(False), "notices")
        self.assertIn("Create notice", out)
        self.assertIn("project:acme raid:r", out)
        self.assertIn("1h 8h 1d 3d", out)

    def _idea(self, **overrides):
        idea = {
            "id": 1,
            "title": "Dark mode",
            "description": "night owls",
            "requester": "ana",
            "deadline": "2000-01-01",
            "project": "acme",
            "dates": "created 2026-10-01 10:00",
            "overdue": True,
            "parties": [],
            "adventurers": [],
        }
        return dict(idea, **overrides)

    def test_ideas_render_with_meta_and_overdue_mark(self):
        board = dict(self._board(False), ideas=[self._idea()])
        out = self._rendered(board, "ideas")
        for expected in (
            "#1 Dark mode",
            "night owls",
            "from ana",
            "due 2000-01-01 (overdue)",
            "Edit",
            "Delete",
            "Add idea",
        ):
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

    def test_idea_shows_linked_adventurers_with_state_and_unlink(self):
        idea = self._idea(
            adventurers=[
                {"id": 3, "state": "active", "has_prs": False},
                {"id": 4, "state": "done", "has_prs": False},
                {"id": 5, "state": "active", "has_prs": True},
            ]
        )
        board = dict(self._board(False), ideas=[idea])
        out = self._rendered(board, "ideas")
        for expected in ("worked by:", "adventurer 3", "adventurer 4 (done)", "adventurer 5"):
            self.assertIn(expected, out)
        self.assertNotIn("not linked yet", out)
        unlinks = [n for n in self._tree_nodes(_render(board, "all", "all", "ideas", "tree")) if n["text"] == "Unlink"]
        self.assertEqual(len(unlinks), 2)

    def _link_options(self, board):
        nodes = self._tree_nodes(_render(board, "all", "all", "ideas", "tree"))
        return [(n["value"], n["text"]) for n in nodes if n["tag"] == "option"]

    def test_link_select_offers_active_adventurers_not_yet_linked(self):
        idea = self._idea(adventurers=[{"id": 3, "state": "active", "has_prs": False}])
        board = dict(
            self._board(False),
            ideas=[idea],
            adventurers=[_adventurer(id=3), _adventurer(id=7), _adventurer(id=8, state="done", pending="x")],
        )
        options = self._link_options(board)
        self.assertIn(("adventurer:7", "adventurer 7"), options)
        self.assertIn(("party:c", "c"), options)
        self.assertNotIn("adventurer:3", [value for value, _ in options])
        self.assertNotIn("adventurer:8", [value for value, _ in options])

    def test_link_posts_the_adventurer_as_a_number(self):
        self.assertIn("{ adventurer: Number(holder) }", _APP_JS)
        self.assertIn("{ party: holder }", _APP_JS)

    def test_party_tracking_a_pr_has_no_unlink_while_another_keeps_it(self):
        idea = self._idea(
            parties=[
                {"name": "a", "state": "active", "has_prs": True},
                {"name": "b", "state": "active", "has_prs": False},
            ]
        )
        tree = json.loads(_render(dict(self._board(False), ideas=[idea]), "all", "all", "ideas", "tree"))
        unlinks = [n for n in self._tree_nodes(json.dumps(tree)) if n["text"] == "Unlink"]
        self.assertEqual(len(unlinks), 1)

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
            "id": 1,
            "party": None,
            "author": "unbound session",
            "scope": "guild",
            "text": "pipeline down",
            "issued_at": "now",
            "issued": "now",
            "expires_at": "later",
            "time_left": "1h left",
            "seen": False,
        }
        board = dict(self._board(False), notices=[notice])
        out = self._rendered(board, "notices")
        self.assertIn("unbound session", out)
        self.assertNotIn("human", out)

    def test_flagged_notice_shows_the_flagged_badge(self):
        notice = {
            "id": 1,
            "party": None,
            "author": "unbound session",
            "scope": "guild",
            "text": "orden del dev",
            "issued_at": "now",
            "issued": "now",
            "expires_at": "later",
            "time_left": "1h left",
            "seen": False,
            "flagged": True,
        }
        board = dict(self._board(False), notices=[notice])
        out = self._rendered(board, "notices")
        self.assertIn("flagged", out)

    def test_unflagged_notice_has_no_flagged_badge(self):
        notice = {
            "id": 1,
            "party": None,
            "author": "unbound session",
            "scope": "guild",
            "text": "pipeline down",
            "issued_at": "now",
            "issued": "now",
            "expires_at": "later",
            "time_left": "1h left",
            "seen": False,
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
        parties = [dict(_BOARD["parties"][0], name="a", state=state, has_live_leader=has_live_leader)]
        board = dict(_BOARD, parties=parties)
        return _render(board, "all", "all", "parties", "text").strip()

    def test_active_party_with_no_live_leader_shows_the_hand_off_button(self):
        self.assertIn("Hand off", self._rendered("active", False))

    def test_active_party_with_a_live_leader_has_no_hand_off_button(self):
        self.assertNotIn("Hand off", self._rendered("active", True))

    def test_non_active_party_has_no_hand_off_button(self):
        self.assertNotIn("Hand off", self._rendered("awaiting-leader", False))


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebPartyParkBehaviorTests(unittest.TestCase):
    def _rendered(self, state, parked, status):
        party = dict(_BOARD["parties"][0], name="a", state=state, parked=parked, status=status)
        return _render(dict(_BOARD, parties=[party]), "all", "all", "parties", "text").strip()

    def test_idle_party_shows_the_park_button(self):
        text = self._rendered("active", None, {"name": "idle", "label": "idle"})
        self.assertIn("Park", text)
        self.assertNotIn("Unpark", text)

    def test_parked_party_shows_the_reason_and_the_unpark_button(self):
        status = {"name": "parked", "label": "parked 3h", "detail": "legal answer"}
        text = self._rendered("awaiting-leader", "legal answer", status)
        self.assertIn("parked 3h", text)
        self.assertIn("legal answer", text)
        self.assertIn("Unpark", text)

    def test_blocked_party_shows_the_blocked_detail(self):
        status = {"name": "blocked", "label": "blocked", "detail": "2 blocked: 2 — ci"}
        self.assertIn("2 blocked: 2 — ci", self._rendered("active", None, status))

    def test_closed_party_has_no_park_button(self):
        self.assertNotIn("Park", self._rendered("closed", None, {"name": "closed", "label": "closed"}))


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
            "tid": "T01",
            "title": "First",
            "state": task_state,
            "summary": None,
            "blocked_reason": None,
            "card_url": None,
            "prs": [],
        }
        quest = {"slug": "src", "title": "Src", "move_targets": move_targets, "tasks": [task], "discarded": []}
        parties = [dict(_BOARD["parties"][0], name="a", quests=[quest])]
        return _render(dict(_BOARD, parties=parties), "all", "all", "parties", "text").strip()

    def test_queued_task_lists_the_move_targets(self):
        out = self._rendered("queued", [{"slug": "dst", "open": False}, {"slug": "dst2", "open": True}])
        self.assertIn("move to...", out)
        self.assertIn("dst2 (open)", out)

    def test_blocked_task_can_move(self):
        self.assertIn("move to...", self._rendered("blocked", [{"slug": "dst", "open": False}]))

    def test_active_task_has_no_move_control(self):
        self.assertNotIn("move to...", self._rendered("active", [{"slug": "dst", "open": False}]))

    def test_no_targets_means_no_move_control(self):
        self.assertNotIn("move to...", self._rendered("queued", []))


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebTaskDiscardBehaviorTests(unittest.TestCase):
    def _rendered(self, task_state, discarded):
        task = {
            "tid": "T01",
            "title": "First",
            "state": task_state,
            "summary": None,
            "blocked_reason": None,
            "card_url": None,
            "prs": [],
        }
        quest = {"slug": "src", "title": "Src", "move_targets": [], "tasks": [task], "discarded": discarded}
        parties = [dict(_BOARD["parties"][0], name="a", quests=[quest])]
        return _render(dict(_BOARD, parties=parties), "all", "all", "parties", "text").strip()

    def test_unfinished_task_has_a_discard_button(self):
        self.assertIn("Discard", self._rendered("queued", []))
        self.assertIn("Discard", self._rendered("active", []))

    def test_done_task_has_no_discard_button(self):
        self.assertNotIn("Discard", self._rendered("done", []))

    def test_discarded_list_shows_count_reason_author_and_restore(self):
        discarded = [
            {"tid": "T02", "title": "Wrong", "reason": "made by mistake", "by": "human", "at": "2026-11-05T10:00:00Z"}
        ]
        out = self._rendered("queued", discarded)
        self.assertIn("Discarded (1)", out)
        self.assertIn("made by mistake", out)
        self.assertIn("discarded by human", out)
        self.assertIn("Restore", out)

    def test_no_discarded_tasks_means_no_list(self):
        self.assertNotIn("Discarded (", self._rendered("queued", []))


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
        quest = {
            "slug": "q1",
            "title": "Quest",
            "move_targets": [],
            "tasks": [],
            "discarded": [],
            "close_blockers": close_blockers,
        }
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
        "ref": ref,
        "title": "T " + ref,
        "url": "https://example.test/" + ref,
        "party": party,
        "scope": scopes[0],
        "scopes": scopes,
        "review_first": review_first,
        "checks": "1 passing",
        "notes": notes,
    }


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebReadyForYouBehaviorTests(unittest.TestCase):
    _ITEMS = [
        _ready_item("o/r#2", "a", ["party:a"], True, ["CI label x not on the PR"]),
        _ready_item("o/r#1", "c", ["raid:r", "raid:r2"], False, []),
        _ready_item("o/r#3", "a", ["party:a"], False, []),
    ]

    def _text(self, items, party_filter, raid_filter, mode):
        return _render(
            dict(
                _BOARD, ready_for_you=items, raids=[{"name": name, "members": ["c"]} for name in ("r", "r2", "other")]
            ),
            party_filter,
            raid_filter,
            "ready-for-you",
            mode,
        ).strip()

    def test_items_render_in_the_given_order(self):
        text = self._text(self._ITEMS, "all", "all", "text")
        self.assertEqual(
            [text.index(ref) for ref in ("o/r#2", "o/r#1", "o/r#3")],
            sorted(text.index(ref) for ref in ("o/r#2", "o/r#1", "o/r#3")),
        )
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


class WebSoloTodoBehaviorTests(unittest.TestCase):
    _SOLO_READY = {
        "ref": "o/r#9",
        "title": "Bump z",
        "url": "https://github.com/o/r/pull/9",
        "party": None,
        "from": "bumper",
        "scope": None,
        "scopes": [],
        "review_first": False,
        "checks": "",
        "notes": [],
    }
    _SOLO_PENDING = {"name": "bumper", "class": "artificer", "repo": "o/r", "pending": "PR 9 needs a human"}

    def _text(self, out_id, party_filter, raid_filter, **overrides):
        return _render(dict(_BOARD, **overrides), party_filter, raid_filter, out_id, "text")

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_ready_row_shows_the_player_name(self):
        text = self._text("ready-for-you", "all", "all", ready_for_you=[self._SOLO_READY])
        self.assertIn("o/r#9", text)
        self.assertIn("from bumper", text)

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_ready_row_is_hidden_by_party_and_raid_filters(self):
        for party_filter, raid_filter in (("a", "all"), ("all", "r")):
            with self.subTest(party=party_filter, raid=raid_filter):
                text = self._text("ready-for-you", party_filter, raid_filter, ready_for_you=[self._SOLO_READY])
                self.assertNotIn("o/r#9", text)

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_ready_badge_counts_the_solo_row(self):
        text = self._text("sidebar", "all", "all", ready_for_you=[self._SOLO_READY])
        self.assertIn("1 ready", text)

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_needs_you_lists_the_pending_item(self):
        text = self._text("asks", "all", "all", solo_pending=[self._SOLO_PENDING])
        self.assertIn("solo (1)", text)
        self.assertIn("[artificer] o/r", text)
        self.assertIn("PR 9 needs a human", text)
        self.assertNotIn("nothing needs you", text)

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_needs_you_hides_the_pending_item_in_a_party_view(self):
        text = self._text("asks", "a", "all", solo_pending=[self._SOLO_PENDING])
        self.assertNotIn("PR 9 needs a human", text)
        self.assertIn("nothing needs you", text)


_QUEST_BOARD = {
    "open_quests": [
        {
            "slug": "pre",
            "epic": "demo",
            "title": "Pre work",
            "left_by": "alpha",
            "dates": "created 2026-10-24 09:00",
            "tasks": [
                {"tid": "T01", "title": "First", "adventurer": None},
                {"tid": "T02", "title": "Second", "adventurer": 7},
            ],
        }
    ],
    "free_tasks": [{"epic": "demo", "tasks": [{"tid": "T03", "title": "Third"}, {"tid": "T04", "title": "Fourth"}]}],
    "parties": ["a", "c"],
    "name": "acme",
}


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebQuestBoardBehaviorTests(unittest.TestCase):
    def _text(self, quest_board, out_id="quest-board"):
        board = dict(_BOARD, quest_boards=[quest_board])
        return _render(board, "all", "all", out_id, "text")

    def test_lists_open_quest_tasks_and_marks_the_held_one(self):
        out = self._text(_QUEST_BOARD)
        for expected in (
            "quest board",
            "acme",
            "pre",
            "Pre work",
            "T01 First",
            "T02 Second (held by adventurer 7)",
            "Assign",
        ):
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
            quest = {
                "slug": "q",
                "title": "Q",
                "tasks": [],
                "discarded": [],
                "close_blockers": None,
                "move_targets": [],
                "releasable": releasable,
            }
            return [dict(_BOARD["parties"][0], quests=[quest])]

        shown = _render(dict(_BOARD, parties=parties(True)), "all", "all", "parties", "text")
        hidden = _render(dict(_BOARD, parties=parties(False)), "all", "all", "parties", "text")
        self.assertIn("Release", shown)
        self.assertNotIn("Release", hidden)

    def test_open_quest_shows_dates_only_when_known(self):
        self.assertIn("created 2026-10-24 09:00", self._text(_QUEST_BOARD))
        undated = dict(_QUEST_BOARD, open_quests=[dict(_QUEST_BOARD["open_quests"][0], dates=None)])
        self.assertNotIn("created", self._text(undated))

    def test_open_quest_shows_who_left_it_only_when_known(self):
        self.assertIn("left by alpha", self._text(_QUEST_BOARD))
        unknown = dict(_QUEST_BOARD, open_quests=[dict(_QUEST_BOARD["open_quests"][0], left_by=None)])
        self.assertNotIn("left by", self._text(unknown))

    def test_party_lists_the_quests_it_left(self):
        followup = {"slug": "later", "title": "Later work", "state": "no party yet"}
        with_followup = dict(_BOARD, parties=[dict(_BOARD["parties"][0], followups=[followup])])
        self.assertIn(
            "left: later — Later work (no party yet)", _render(with_followup, "all", "all", "parties", "text")
        )
        self.assertNotIn("left: ", _render(_BOARD, "all", "all", "parties", "text"))

    def test_party_quest_and_task_show_dates_only_when_known(self):
        def rendered(quest_dates, task_dates):
            task = {
                "tid": "T01",
                "title": "First",
                "state": "active",
                "dates": task_dates,
                "summary": None,
                "blocked_reason": None,
                "card_url": None,
                "prs": [],
            }
            quest = {
                "slug": "q",
                "title": "Q",
                "dates": quest_dates,
                "tasks": [task],
                "discarded": [],
                "close_blockers": None,
                "move_targets": [],
                "releasable": False,
            }
            parties = [dict(_BOARD["parties"][0], quests=[quest])]
            return _render(dict(_BOARD, parties=parties), "all", "all", "parties", "text")

        shown = rendered("created QUESTDATE", "created TASKDATE")
        self.assertIn("QUESTDATE", shown)
        self.assertIn("TASKDATE", shown)
        hidden = rendered(None, None)
        self.assertNotIn("QUESTDATE", hidden)
        self.assertNotIn("TASKDATE", hidden)

    def test_party_pr_shows_the_behind_pill_only_when_behind(self):
        def rendered(behind):
            pr = {
                "repo": "o/r",
                "number": 1,
                "lifecycle": "ready",
                "task": None,
                "needs_ask_answer": False,
                "ask_id": None,
                "needs_human_pr_review": False,
                "fixes_main": False,
                "fixes_flaky": False,
                "blocked_external": None,
                "party": "a",
                "checks_failing": 0,
                "checks_passing": 0,
                "checks_pending": 0,
                "what": "w",
                "waits": None,
                "branch": None,
                "base_branch": None,
                "review_reasons": [],
                "behind": behind,
                "card": None,
                "card_url": None,
                "dates": None,
                "url": "https://example.com/pr",
            }
            party = dict(_BOARD["parties"][0], prs=[pr])
            return _render(dict(_BOARD, parties=[party]), "all", "all", "parties", "text")

        self.assertIn("3 behind main", rendered("3 behind main"))
        self.assertNotIn("behind", rendered(None))

    def test_party_pr_and_claim_show_dates_only_when_known(self):
        def rendered(party_dates, pr_dates, claim_dates):
            pr = {
                "repo": "o/r",
                "number": 1,
                "lifecycle": "ready",
                "needs_ask_answer": False,
                "ask_id": None,
                "needs_human_pr_review": False,
                "fixes_main": False,
                "fixes_flaky": False,
                "blocked_external": None,
                "party": "a",
                "checks_failing": 0,
                "checks_passing": 0,
                "checks_pending": 0,
                "what": "w",
                "waits": None,
                "branch": None,
                "base_branch": None,
                "review_reasons": [],
                "card": None,
                "card_url": None,
                "dates": pr_dates,
                "url": "https://example.com/pr",
            }
            claim = {"area": "src/x", "expires_at": "2026-10-24T11:00:00+00:00", "dates": claim_dates}
            party = dict(_BOARD["parties"][0], dates=party_dates, prs=[pr], claims=[claim])
            return _render(dict(_BOARD, parties=[party]), "all", "all", "parties", "text")

        shown = rendered("created PARTYDATE", "created PRDATE", "created CLAIMDATE")
        for expected in ("PARTYDATE", "PRDATE", "src/x (created CLAIMDATE)"):
            self.assertIn(expected, shown)
        hidden = rendered(None, None, None)
        for unexpected in ("PARTYDATE", "PRDATE", "CLAIMDATE"):
            self.assertNotIn(unexpected, hidden)
        self.assertIn("claims: src/x", hidden)

    def test_writes_go_through_send_post(self):
        for expected in (
            '"/api/quests/create-open"',
            '"/api/quests/" + quest.slug + "/take"',
            '"/api/quests/" + quest.slug + "/release"',
        ):
            self.assertIn(expected, _APP_JS)


def _flatten(node):
    yield node
    for child in node["children"]:
        yield from _flatten(child)


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebAskTextBehaviorTests(unittest.TestCase):
    def _asks_tree(self, context_text, recommend):
        ask = _ask(context=context_text, recommend=recommend)
        rendered = _render(dict(_BOARD, asks=[ask]), "all", "all", "asks", "tree")
        return list(_flatten(json.loads(rendered)))

    def test_context_builds_paragraphs_breaks_and_bold(self):
        nodes = self._asks_tree("one\ntwo **bold**\n\nthree", None)
        self.assertEqual(sum(1 for node in nodes if node["tag"] == "br"), 1)
        self.assertEqual(
            [node["text"] for node in nodes if node["tag"] == "strong" and node["text"] == "bold"], ["bold"]
        )
        self.assertEqual(
            sum(
                1 for node in nodes if node["tag"] == "p" and node["children"] and node["children"][0]["tag"] == "#text"
            ),
            2,
        )

    def test_markup_in_text_stays_text(self):
        nodes = self._asks_tree("<script>x</script>", None)
        self.assertFalse([node for node in nodes if node["tag"] == "script"])
        self.assertIn("<script>x</script>", [node["text"] for node in nodes])

    def test_recommend_shows_only_when_set(self):
        shown = self._asks_tree("ctx", "do **this**")
        self.assertTrue([node for node in shown if node["className"] == "ask-recommend"])
        hidden = self._asks_tree("ctx", None)
        self.assertFalse([node for node in hidden if node["className"] == "ask-recommend"])


def _render_opened(board, out_id, responses, open_summaries):
    return node_harness.request(
        _HARNESS_NAME,
        {
            "src": str(_APP_JS_PATH),
            "data": board,
            "hash": _view_hash("all", "all"),
            "outId": out_id,
            "mode": "tree",
            "responses": responses,
            "open": open_summaries,
        },
    )


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebMultilineAnswerBehaviorTests(unittest.TestCase):
    def _breaks(self, rendered):
        return sum(1 for node in _flatten(json.loads(rendered)) if node["tag"] == "br")

    def test_answered_list_keeps_answer_line_breaks(self):
        answered_model = {
            "asks": [
                {"id": 5, "party": "alpha", "question": "Q", "answer": "one\ntwo", "answered_at": None, "dates": None}
            ],
            "total": 1,
            "page": 1,
            "page_count": 1,
        }
        rendered = _render_opened(
            _BOARD, "answered-asks", {"/api/asks/answered?page=1": answered_model}, ["answered asks"]
        )
        self.assertEqual(self._breaks(rendered), 1)

    def test_ask_detail_keeps_answer_line_breaks(self):
        detail_model = {"refs": [], "origin": None, "resume": None, "answer": "one\ntwo\nthree"}
        rendered = _render_opened(
            dict(_BOARD, asks=[_ask(context="ctx", recommend=None)]), "asks", {"/api/asks/3": detail_model}, ["detail"]
        )
        self.assertEqual(self._breaks(rendered), 2)


def _leaf_text(node):
    if not node["children"]:
        return node["text"]
    return node["text"] + "".join(_leaf_text(child) for child in node["children"])


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebBlockedLineBehaviorTests(unittest.TestCase):
    def _line(self, detail):
        entry = {
            "party": "alpha",
            "wait": "permission",
            "since": None,
            "detail": detail,
            "label": "waiting-permission 27m",
        }
        tree = json.loads(_render(dict(_BOARD, blocked=[entry]), "all", "all", "asks", "tree"))
        lines = [node for node in _flatten(tree) if node["className"] == "blocked-session"]
        return _leaf_text(lines[0])

    def test_party_status_and_detail_are_separated(self):
        self.assertEqual(
            self._line("Claude needs your permission"),
            "alpha · waiting-permission 27m · Claude needs your permission",
        )

    def test_no_trailing_separator_without_detail(self):
        self.assertEqual(self._line(None), "alpha · waiting-permission 27m")
