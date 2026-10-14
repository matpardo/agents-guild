import os
import subprocess

from guild import db, events, handoff_prune, identity, names, party_status, paths, pii, render, resume
from guild import timeutil, tmux_windows
from guild.commands import claim as claim_commands
from guild.commands import memory as memory_commands
from guild.commands import next as next_commands
from guild.commands import notice as notice_commands
from guild.errors import GuildError

_AUTO_LEARNED = "none (automatic handoff)"

IN_FLIGHT_TITLE = "In flight"
LEARNED_TITLE = "Learned"


def _section(title, lines):
    return ["## {}".format(title), *lines, ""]


def _quest_lines(conn, party):
    quests = conn.execute(
        "SELECT slug, title FROM quests WHERE party = ? AND state = 'active' ORDER BY slug ASC",
        (party,),
    ).fetchall()
    return ["- {} — {}".format(row["slug"], row["title"]) for row in quests]


def _pr_lines(conn, party):
    rows = conn.execute(
        "SELECT * FROM prs WHERE party = ? ORDER BY repo ASC, number ASC", (party,)
    ).fetchall()
    return ["- {}".format(render.pr_line(row)) for row in rows]


def _ask_lines(conn, party):
    rows = conn.execute(
        "SELECT id, question FROM asks WHERE party = ? AND state = 'open' ORDER BY id ASC",
        (party,),
    ).fetchall()
    return ["- #{}: {}".format(row["id"], row["question"]) for row in rows]


def _notice_lines(conn, now, party):
    rows = [row for row in notice_commands.active_notices(conn, now) if row["party"] == party]
    return [
        "- #{} ({}): {}".format(row["id"], timeutil.issued_label(row["created_at"]), row["text"])
        for row in rows
    ]


def _claim_lines(conn, now, party):
    rows = [row for row in claim_commands.list_claims(conn, now) if row["party"] == party]
    return ["- {} until {}".format(row["area"], row["expires_at"]) for row in rows]


def _render_handoff(ctx, binding, in_flight, learned):
    lines = ["# Handoff: {} (generation {})".format(binding["party"], binding["generation"]), ""]
    lines += _section("Quest", _quest_lines(ctx.conn, binding["party"]))
    lines += _section(
        "Next", ["- {}".format(line) for line in next_commands.run(ctx, binding, True, False)]
    )
    lines += _section("PRs", _pr_lines(ctx.conn, binding["party"]))
    lines += _section("Open asks", _ask_lines(ctx.conn, binding["party"]))
    lines += _section("Active notices", _notice_lines(ctx.conn, ctx.now, binding["party"]))
    lines += _section("Claims", _claim_lines(ctx.conn, ctx.now, binding["party"]))
    lines += _section(IN_FLIGHT_TITLE, [in_flight])
    lines += _section(LEARNED_TITLE, [learned])
    return "\n".join(lines) + "\n"


def _with_reminder(text):
    return "{}\n{}".format(text, pii.BROADCAST_REMINDER)


def _write_handoff(ctx, binding, in_flight, learned, auto):
    party, generation = binding["party"], binding["generation"]
    content = _render_handoff(ctx, binding, in_flight, learned)
    handoffs_dir = paths.handoffs_dir()
    handoff_path = handoffs_dir / "{}-g{}.md".format(party, generation)
    handoffs_dir.mkdir(parents=True, exist_ok=True)
    handoff_path = names.ensure_within(handoff_path, handoffs_dir)
    handoff_path.write_text(content)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            party,
            ctx.session_id,
            binding["project"],
            "party.handed_off",
            "local",
            {"party": party, "generation": generation, "handoff_path": str(handoff_path), "auto": auto},
        )


def _for_memory(text):
    if len(text) <= pii.MEMORY_ITEM_MAX_LENGTH:
        return text
    return text[: pii.MEMORY_ITEM_MAX_LENGTH - 1] + "…"


def _closable_pane(tmux, tmux_pane, recorded_window):
    if tmux_pane is None or recorded_window is None:
        return None
    own_window = tmux_windows.window_id_of_pane(tmux, tmux_pane)
    if own_window != recorded_window:
        return None
    if not tmux_windows.window_in_session(tmux, own_window):
        return None
    return tmux_pane


def _close(ctx, binding, tmux, tmux_pane):
    recorded_window = tmux_windows.recorded_window(ctx.conn, binding["party"], binding["generation"])
    pane = _closable_pane(tmux, tmux_pane, recorded_window)
    label = "{}-g{}".format(binding["party"], binding["generation"])
    if pane is None:
        return _with_reminder("handoff written for {}; not a window guild launched, close it yourself".format(label)), None
    return _with_reminder("handoff written for {}; closing this pane".format(label)), pane


def run(ctx, in_flight, learned, model, close, tmux, tmux_pane):
    if not in_flight.strip():
        raise GuildError("--in-flight must not be empty", 1)
    if not learned.strip():
        raise GuildError("--learned must not be empty", 1)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    patterns = pii.project_patterns(ctx.projects_dir, binding["project"])
    pii.validate_field(in_flight, "--in-flight", pii.HANDOFF_FIELD_MAX_LENGTH, patterns)
    pii.validate_field(learned, "--learned", pii.HANDOFF_FIELD_MAX_LENGTH, patterns)
    memory_commands.add(ctx, _for_memory(learned))
    _write_handoff(ctx, binding, in_flight, learned, False)
    if close:
        return _close(ctx, binding, tmux, tmux_pane)
    command = resume.fresh_command(
        binding["party"],
        binding["generation"] + 1,
        model,
        None,
        resume.RESUME_PROMPT,
    )
    return _with_reminder(command), None


def _dry_run_text(ctx):
    prune_plan = handoff_prune.plan(ctx, paths.handoffs_dir(), ctx.state_dir)
    return "\n".join(handoff_prune.report_lines(prune_plan, True))


def _real_run_text(ctx):
    with handoff_prune.lock(ctx) as acquired:
        if not acquired:
            return "prune already running"
        prune_plan = handoff_prune.plan(ctx, paths.handoffs_dir(), ctx.state_dir)
        result = handoff_prune.apply(ctx, prune_plan.actions)
    lines = handoff_prune.report_lines(prune_plan, False)
    lines.extend("skip {}: {}".format(action.label, action.reason) for action in result.skipped)
    return "\n".join(lines)


def run_prune(ctx, dry_run):
    if dry_run:
        return _dry_run_text(ctx)
    return _real_run_text(ctx)


def _run_git(args, cwd):
    try:
        result = subprocess.run(["git", "-C", str(cwd)] + list(args), capture_output=True, text=True)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _is_git_repo(cwd):
    return _run_git(["rev-parse", "--git-dir"], cwd) is not None


def _branch(cwd):
    out = _run_git(["branch", "--show-current"], cwd)
    return None if out is None else (out.strip() or None)


def _uncommitted_count(cwd):
    out = _run_git(["status", "--porcelain"], cwd)
    if out is None:
        return None
    return len([line for line in out.splitlines() if line.strip()])


def _unpushed_count(cwd):
    out = _run_git(["rev-list", "--count", "@{u}..HEAD"], cwd)
    if out is None:
        return None
    stripped = out.strip()
    return int(stripped) if stripped.isdigit() else None


def _count_or_unknown(count, noun):
    if count is None:
        return "{} unknown".format(noun)
    return "{} {}".format(count, noun)


def _auto_in_flight(cwd):
    if cwd is None or not os.path.isdir(cwd) or not _is_git_repo(cwd):
        return "automatic handoff: worktree unknown"
    return "automatic handoff: branch {}, {}, {}".format(
        _branch(cwd) or "unknown",
        _count_or_unknown(_uncommitted_count(cwd), "uncommitted"),
        _count_or_unknown(_unpushed_count(cwd), "unpushed"),
    )


def write_auto(ctx, binding):
    leader = ctx.conn.execute(
        "SELECT cwd FROM leaders WHERE party = ? AND generation = ?",
        (binding["party"], binding["generation"]),
    ).fetchone()
    cwd = None if leader is None else leader["cwd"]
    in_flight = _auto_in_flight(cwd)
    patterns = pii.project_patterns(ctx.projects_dir, binding["project"])
    pii.validate_field(in_flight, "--in-flight", pii.HANDOFF_FIELD_MAX_LENGTH, patterns)
    _write_handoff(ctx, binding, in_flight, _AUTO_LEARNED, True)


def _party_row_for_handoff(conn, party):
    row = conn.execute("SELECT * FROM parties WHERE name = ?", (party,)).fetchone()
    if row is None:
        raise GuildError("unknown party '{}'".format(party), 1)
    if row["state"] == "closed":
        raise GuildError("party '{}' is closed".format(party), 1)
    return row


def run_for_party(ctx, party):
    names.validate_name(party, "party name")
    party_row = _party_row_for_handoff(ctx.conn, party)
    if party_status.has_live_leader(ctx, party_row):
        raise GuildError(
            "party '{}' has a live leader: run `guild handoff` from that session instead".format(party), 1
        )
    binding = {"party": party_row["name"], "project": party_row["project"], "generation": party_row["generation"]}
    write_auto(ctx, binding)
    return "handoff written for '{}', generation {}".format(party_row["name"], party_row["generation"])
