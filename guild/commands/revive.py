import json
import os

from guild import db, events, party_status, resume, tmux_windows
from guild.errors import GuildError

TRANSCRIPT_LINE_LIMIT = 200
_NO_SELECTION_HINT = "select with --party <name> (repeatable), --all, or --list for copy-paste commands"
_GOAL_REMINDER = "re-issue /goal in each revived session that used it: it is not restored"
_TMUX_MISSING = "tmux not found: install tmux (e.g. sudo apt install tmux) or use --list"


class _Entry:
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
    ):
        self.party = party
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

    def resumable(self):
        return self.transcript is not None

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


def find_transcript(projects_dir, session_id):
    if session_id is None:
        return None
    matches = sorted(projects_dir.glob("*/{}.jsonl".format(session_id)))
    if not matches:
        return None
    return matches[0]


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


def _quest_label(conn, party):
    quests = conn.execute(
        "SELECT slug FROM quests WHERE party = ? AND state = 'active' ORDER BY slug ASC", (party,)
    ).fetchall()
    if not quests:
        return "no active quest"
    labels = []
    for quest in quests:
        counts = conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(state = 'done'), 0) AS done"
            " FROM quest_tasks WHERE quest = ?",
            (quest["slug"],),
        ).fetchone()
        labels.append("{} {}/{}".format(quest["slug"], counts["done"], counts["total"]))
    return ", ".join(labels)


def _entry(ctx, transcripts_dir, party):
    leader = ctx.conn.execute(
        "SELECT * FROM leaders WHERE party = ? AND generation = ?",
        (party["name"], party["generation"]),
    ).fetchone()
    session_id = party["leader_session_id"]
    transcript = find_transcript(transcripts_dir, session_id)
    cwd = None if leader is None else leader["cwd"]
    mode = None if leader is None else leader["permission_mode"]
    if transcript is not None and (cwd is None or mode is None):
        transcript_cwd, transcript_mode = read_location(transcript)
        cwd = cwd or transcript_cwd
        mode = mode or transcript_mode
    last_activity = ctx.conn.execute(
        "SELECT MAX(ts) AS ts FROM events WHERE party = ?", (party["name"],)
    ).fetchone()["ts"]
    return _Entry(
        party["name"],
        party["project"],
        party["generation"],
        session_id,
        None if leader is None else leader["session_name"],
        _quest_label(ctx.conn, party["name"]),
        party_status.label(ctx, party_status.derive(ctx, party)),
        last_activity,
        cwd,
        mode,
        None if party["state"] == "awaiting-leader" else transcript,
    )


def _entries(ctx, transcripts_dir):
    parties = ctx.conn.execute(
        "SELECT * FROM parties WHERE state IN ('active', 'awaiting-leader') ORDER BY name ASC"
    ).fetchall()
    return [_entry(ctx, transcripts_dir, party) for party in parties]


def _listing_lines(entries, with_commands):
    lines = []
    for number, entry in enumerate(entries, start=1):
        lines.append(
            "{}. {} ({}) [{}]".format(
                number, entry.party, entry.project or "-", "resume" if entry.resumable() else "fresh"
            )
        )
        lines.append("   quest: {} | last activity: {}".format(entry.quests, entry.last_activity or "-"))
        lines.append("   status: {}".format(entry.status))
        lines.append("   session: {} | mode: {}".format(entry.session_name or "-", entry.mode_label()))
        lines.append("   cwd: {}".format(entry.cwd or "unknown"))
        if with_commands:
            lines.append("   tab: {}".format(_tab_line(entry)))
    return lines


def _tab_line(entry):
    if entry.cwd is None:
        return "cwd unknown"
    return resume.tab_command(entry.party, entry.cwd, entry.command())


def _parse_numbers(answer, entries):
    selected = []
    for token in answer.replace(",", " ").split():
        if not token.isdigit() or not 1 <= int(token) <= len(entries):
            raise GuildError("invalid selection '{}': use numbers 1-{}".format(token, len(entries)), 1)
        entry = entries[int(token) - 1]
        if entry not in selected:
            selected.append(entry)
    return selected


def _select_by_name(entries, party_names):
    by_name = {entry.party: entry for entry in entries}
    for name in party_names:
        if name not in by_name:
            raise GuildError("party '{}' is not active".format(name), 1)
    return [entry for entry in entries if entry.party in party_names]


def _skip_reason(entry, windows):
    if entry.party in windows:
        return "window already exists"
    if entry.cwd is None:
        return "cwd unknown; start a fresh session from the project path"
    if not os.path.isdir(entry.cwd):
        return "cwd missing ({}); start a fresh session from the project path".format(entry.cwd)
    return None


def _record_window(ctx, entry, window_id):
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            entry.party,
            None,
            entry.project,
            "leader.window_launched",
            "local",
            {"party": entry.party, "generation": entry.launch_generation(), "window_id": window_id},
        )


def _launch_line(ctx, tmux, entry, session_is_up):
    window_id = tmux_windows.create_window(tmux, entry.party, entry.cwd, entry.command(), session_is_up)
    if window_id is None:
        return "failed {}: tmux could not create the window".format(entry.party), False
    _record_window(ctx, entry, window_id)
    if not tmux_windows.pin_window_name(tmux, window_id):
        return "failed {}: window created but its name could not be pinned".format(entry.party), True
    return "launched {} ({})".format(entry.party, "resume" if entry.resumable() else "fresh"), True


def _launch(ctx, tmux, selected):
    if not tmux.installed():
        raise GuildError(_TMUX_MISSING, 1)
    session_is_up = tmux_windows.session_exists(tmux)
    windows = tmux_windows.window_names(tmux) if session_is_up else set()
    lines = []
    for entry in selected:
        reason = _skip_reason(entry, windows)
        if reason is not None:
            lines.append("skipped {}: {}".format(entry.party, reason))
            continue
        line, window_created = _launch_line(ctx, tmux, entry, session_is_up)
        lines.append(line)
        session_is_up = session_is_up or window_created
    if session_is_up:
        tmux_windows.set_session_options(tmux)
    return lines


def run(ctx, party_names, select_all, list_only, transcripts_dir, tmux, ask_numbers):
    entries = _entries(ctx, transcripts_dir)
    if not entries:
        return "no active parties"
    if list_only:
        return "\n".join(_listing_lines(entries, True))
    if select_all:
        selected = entries
    elif party_names:
        selected = _select_by_name(entries, party_names)
    elif ask_numbers is not None:
        prompt = "\n".join([*_listing_lines(entries, False), "numbers to revive (e.g. 1,3): "])
        selected = _parse_numbers(ask_numbers(prompt), entries)
    else:
        return "\n".join([*_listing_lines(entries, False), _NO_SELECTION_HINT])
    if not selected:
        return "nothing selected"
    lines = _launch(ctx, tmux, selected)
    return "\n".join([*lines, _GOAL_REMINDER, "tmux attach -t {}".format(tmux_windows.SESSION)])
