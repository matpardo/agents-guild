import json
import os
from pathlib import Path

from guild import db, events, localbase, party_status, resume, sanitize, session_info, tmux_windows, transcripts
from guild.errors import GuildError

TRANSCRIPT_LINE_LIMIT = 200
_NO_SELECTION_HINT = (
    "select with --party <name> or --adventurer <id> (repeatable), --all, or --list for copy-paste commands"
)
_GOAL_REMINDER = "re-issue /goal in each revived session that used it: it is not restored"
_TMUX_MISSING = "tmux not found: install tmux (e.g. sudo apt install tmux) or use --list"


class _PartyEntry:
    live_reason = "leader session is live"

    def __init__(
        self,
        party,
        project,
        generation,
        session_id,
        session_name,
        quests,
        status,
        last_activity,
        cwd,
        mode,
        transcript,
        goal,
        live,
    ):
        self.party = party
        self.window = party
        self.live = live
        self.project = project
        self.generation = generation
        self.session_id = session_id
        self.session_name = session_name
        self.quests = quests
        self.status = status
        self.last_activity = last_activity
        self.cwd = cwd
        self.mode = mode
        self.transcript = transcript
        self.goal = goal

    def resumable(self):
        return self.transcript is not None

    def label(self):
        return "resume" if self.resumable() else "fresh"

    def missing_transcript_reason(self):
        return None

    def cwd_advice(self):
        return "start a fresh session from the project path"

    def record_window(self, ctx, window_id):
        with db.writing(ctx.conn):
            events.record(
                ctx.conn,
                ctx.now,
                ctx.origin,
                self.party,
                None,
                self.project,
                "leader.window_launched",
                "local",
                {"party": self.party, "generation": self.launch_generation(), "window_id": window_id},
            )

    def listing_lines(self, number, with_commands):
        lines = [
            "{}. {} ({}) [{}]".format(number, self.party, self.project or "-", self.label()),
            "   quest: {} | last activity: {}".format(self.quests, self.last_activity or "-"),
            "   status: {}".format(self.status),
            "   goal: {}".format(self.goal or "none"),
            "   session: {} | mode: {}".format(self.session_name or "-", self.mode_label()),
            "   cwd: {}".format(self.cwd or "unknown"),
        ]
        if with_commands:
            lines.append("   tab: {}".format(_tab_line(self)))
        return lines

    def launch_generation(self):
        if self.resumable():
            return self.generation
        return self.generation + 1

    def mode_label(self):
        return "unknown" if self.mode is None else self.mode

    def command(self):
        if self.resumable():
            return resume.resume_command(self.session_id, self.party, self.generation, self.mode)
        return resume.fresh_command(self.party, self.generation + 1, None, self.mode, resume.RESUME_PROMPT)


class _AdventurerEntry:
    live_reason = "session is live"

    def __init__(self, row, live, cwd, mode, transcript):
        self.adventurer_id = row["id"]
        self.window = "adventurer-{}".format(row["id"])
        self.project = row["project"]
        self.job = sanitize.strip_control_sequences(row["job"])
        self.task = row["task"]
        self.session_id = row["session_id"]
        self.live = live
        self.cwd = cwd
        self.mode = mode
        self.transcript = transcript

    def label(self):
        return "resume"

    def missing_transcript_reason(self):
        if self.transcript is not None:
            return None
        return "no transcript; {}".format(self.cwd_advice())

    def cwd_advice(self):
        return "dismiss it with guild adventurer dismiss {}".format(self.adventurer_id)

    def command(self):
        return resume.named_resume_command(self.session_id, self.window, self.mode)

    def record_window(self, ctx, window_id):
        return None

    def listing_lines(self, number, with_commands):
        lines = [
            "{}. adventurer {} {} ({}) [resume]".format(number, self.adventurer_id, self.job, self.project),
            "   task: {}".format(self.task or "-"),
            "   mode: {}".format("unknown" if self.mode is None else self.mode),
            "   cwd: {}".format(self.cwd or "unknown"),
        ]
        if with_commands:
            lines.append("   tab: {}".format(_tab_line(self)))
        return lines


def read_location(transcript):
    cwd = None
    permission_mode = None
    with transcript.open() as handle:
        for _ in range(TRANSCRIPT_LINE_LIMIT):
            line = handle.readline()
            if not line:
                break
            record = _parse_record(line)
            cwd = record.get("cwd") or cwd
            permission_mode = record.get("permissionMode") or permission_mode
            if cwd is not None and permission_mode is not None:
                break
    return cwd, permission_mode


def _parse_record(line):
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return {}
    if not isinstance(record, dict):
        return {}
    return record


def _surviving_checkout(cwd):
    for directory in Path(cwd).parents:
        if localbase.is_main_checkout(directory):
            return str(directory)
    return None


def _quest_label(conn, party):
    quests = conn.execute(
        "SELECT slug FROM quests WHERE party = ? AND state = 'active' ORDER BY slug ASC", (party,)
    ).fetchall()
    if not quests:
        return "no active quest"
    labels = []
    for quest in quests:
        counts = conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(state = 'done'), 0) AS done FROM quest_tasks"
            " WHERE quest = ? AND state != 'discarded'",
            (quest["slug"],),
        ).fetchone()
        labels.append("{} {}/{}".format(quest["slug"], counts["done"], counts["total"]))
    return ", ".join(labels)


def _status_label(ctx, party):
    status = party_status.derive(ctx, party)
    label = party_status.label(ctx, status)
    if party["parked"] is None:
        return label
    reason = sanitize.strip_control_sequences(party["parked"])
    if status["status"] == "parked":
        return "{} — {}".format(label, reason)
    return "{} | parked: {}".format(label, reason)


def _entry(ctx, transcripts_dir, party):
    leader = ctx.conn.execute(
        "SELECT * FROM leaders WHERE party = ? AND generation = ?",
        (party["name"], party["generation"]),
    ).fetchone()
    session_id = party["leader_session_id"]
    transcript = transcripts.find_transcript(transcripts_dir, session_id)
    cwd = None if leader is None else leader["cwd"]
    mode = None if leader is None else leader["permission_mode"]
    if transcript is not None and (cwd is None or mode is None):
        transcript_cwd, transcript_mode = read_location(transcript)
        cwd = cwd or transcript_cwd
        mode = mode or transcript_mode
    checkout = None if cwd is None or os.path.isdir(cwd) else _surviving_checkout(cwd)
    if checkout is not None:
        cwd = checkout
        transcript = None
    last_activity = ctx.conn.execute("SELECT MAX(ts) AS ts FROM events WHERE party = ?", (party["name"],)).fetchone()[
        "ts"
    ]
    return _PartyEntry(
        party["name"],
        party["project"],
        party["generation"],
        session_id,
        None if leader is None else leader["session_name"],
        _quest_label(ctx.conn, party["name"]),
        _status_label(ctx, party),
        last_activity,
        cwd,
        mode,
        None if party["state"] == "awaiting-leader" else transcript,
        party["goal"],
        party_status.has_live_leader(ctx, party),
    )


def _adventurer_entry(ctx, transcripts_dir, live_ids, row):
    transcript = transcripts.find_transcript(transcripts_dir, row["session_id"])
    cwd, mode = (None, None) if transcript is None else read_location(transcript)
    return _AdventurerEntry(row, row["session_id"] in live_ids, cwd, mode, transcript)


def _entries(ctx, transcripts_dir):
    parties = ctx.conn.execute(
        "SELECT * FROM parties WHERE state IN ('active', 'awaiting-leader') ORDER BY name ASC"
    ).fetchall()
    adventurers = ctx.conn.execute(
        "SELECT * FROM adventurers WHERE state = 'active' AND health_job IS NULL ORDER BY id ASC"
    ).fetchall()
    live_ids = session_info.live_session_ids(ctx.sessions_dir)
    return [
        *[_entry(ctx, transcripts_dir, party) for party in parties],
        *[_adventurer_entry(ctx, transcripts_dir, live_ids, row) for row in adventurers],
    ]


def _listing_lines(entries, with_commands):
    lines = []
    for number, entry in enumerate(entries, start=1):
        lines.extend(entry.listing_lines(number, with_commands))
    return lines


def _tab_line(entry):
    if entry.cwd is None:
        return "cwd unknown"
    reason = entry.missing_transcript_reason()
    if reason is not None:
        return reason
    return resume.tab_command(entry.window, entry.cwd, entry.command())


def _parse_numbers(answer, entries):
    selected = []
    for token in answer.replace(",", " ").split():
        if not token.isdigit() or not 1 <= int(token) <= len(entries):
            raise GuildError("invalid selection '{}': use numbers 1-{}".format(token, len(entries)), 1)
        entry = entries[int(token) - 1]
        if entry not in selected:
            selected.append(entry)
    return selected


def _select(entries, party_names, adventurer_ids):
    parties = {entry.party: entry for entry in entries if isinstance(entry, _PartyEntry)}
    adventurers = {entry.adventurer_id: entry for entry in entries if isinstance(entry, _AdventurerEntry)}
    for name in party_names:
        if name not in parties:
            raise GuildError("party '{}' is not active".format(name), 1)
    for adventurer_id in adventurer_ids:
        if adventurer_id not in adventurers:
            raise GuildError("adventurer {} is not active".format(adventurer_id), 1)
    chosen = [*[parties[name] for name in party_names], *[adventurers[i] for i in adventurer_ids]]
    return [entry for entry in entries if entry in chosen]


def _skip_reason(entry, windows):
    if entry.live:
        return entry.live_reason
    if entry.window in windows:
        return "window already exists"
    transcript_reason = entry.missing_transcript_reason()
    if transcript_reason is not None:
        return transcript_reason
    if entry.cwd is None:
        return "cwd unknown; {}".format(entry.cwd_advice())
    if not os.path.isdir(entry.cwd):
        return "cwd missing ({}); {}".format(entry.cwd, entry.cwd_advice())
    return None


def _launch_line(ctx, tmux, entry, session_is_up):
    window_id = tmux_windows.create_window(tmux, entry.window, entry.cwd, entry.command(), session_is_up)
    if window_id is None:
        return "failed {}: tmux could not create the window".format(entry.window), False
    entry.record_window(ctx, window_id)
    if not tmux_windows.pin_window_name(tmux, window_id):
        return "failed {}: window created but its name could not be pinned".format(entry.window), True
    return "launched {} ({})".format(entry.window, entry.label()), True


def _launch(ctx, tmux, selected):
    if not tmux.installed():
        raise GuildError(_TMUX_MISSING, 1)
    session_is_up = tmux_windows.session_exists(tmux)
    windows = tmux_windows.window_names(tmux) if session_is_up else set()
    lines = []
    for entry in selected:
        reason = _skip_reason(entry, windows)
        if reason is not None:
            lines.append("skipped {}: {}".format(entry.window, reason))
            continue
        line, window_created = _launch_line(ctx, tmux, entry, session_is_up)
        lines.append(line)
        session_is_up = session_is_up or window_created
    if session_is_up:
        tmux_windows.set_session_options(tmux)
    return lines


def run(ctx, party_names, adventurer_ids, select_all, list_only, transcripts_dir, tmux, ask_numbers):
    entries = _entries(ctx, transcripts_dir)
    if not entries:
        return "nothing to revive"
    if list_only:
        return "\n".join(_listing_lines(entries, True))
    if select_all:
        selected = entries
    elif party_names or adventurer_ids:
        selected = _select(entries, party_names, adventurer_ids)
    elif ask_numbers is not None:
        prompt = "\n".join([*_listing_lines(entries, False), "numbers to revive (e.g. 1,3): "])
        selected = _parse_numbers(ask_numbers(prompt), entries)
    else:
        return "\n".join([*_listing_lines(entries, False), _NO_SELECTION_HINT])
    if not selected:
        return "nothing selected"
    lines = _launch(ctx, tmux, selected)
    return "\n".join([*lines, _GOAL_REMINDER, *tmux_windows.ATTACH_HINT])
