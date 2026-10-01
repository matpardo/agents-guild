import shlex

from guild import db, events, identity, names, paths, pii, render
from guild.commands import claim as claim_commands
from guild.commands import next as next_commands
from guild.commands import notice as notice_commands
from guild.commands import raid as raid_commands
from guild.errors import GuildError


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
    return ["- #{}: {}".format(row["id"], row["text"]) for row in rows]


def _claim_lines(conn, now, party):
    rows = [row for row in claim_commands.list_claims(conn, now) if row["party"] == party]
    return ["- {} until {}".format(row["area"], row["expires_at"]) for row in rows]


def _role_lines(conn, now, party):
    return ["- you lead raid {}".format(raid_name) for raid_name in raid_commands.led_raid_names(conn, now, party)]


def _render_handoff(ctx, binding, in_flight, learned):
    lines = ["# Handoff: {} (generation {})".format(binding["party"], binding["generation"]), ""]
    role_lines = _role_lines(ctx.conn, ctx.now, binding["party"])
    if role_lines:
        lines += _section("Role", role_lines)
    lines += _section("Quest", _quest_lines(ctx.conn, binding["party"]))
    lines += _section(
        "Next", ["- {}".format(line) for line in next_commands.run(ctx, binding, True, False)]
    )
    lines += _section("PRs", _pr_lines(ctx.conn, binding["party"]))
    lines += _section("Open asks", _ask_lines(ctx.conn, binding["party"]))
    lines += _section("Active notices", _notice_lines(ctx.conn, ctx.now, binding["party"]))
    lines += _section("Claims", _claim_lines(ctx.conn, ctx.now, binding["party"]))
    lines += _section("In flight", [in_flight])
    lines += _section("Learned", [learned])
    return "\n".join(lines) + "\n"


_RESUME_PROMPT = "Continue the work described in the guild handoff."


def _resume_command(party, next_generation, model):
    model_flag = "" if model is None else " --model {}".format(shlex.quote(model))
    return "GUILD_RESUME={} claude -n {}-g{}{} {}".format(
        party, party, next_generation, model_flag, shlex.quote(_RESUME_PROMPT)
    )


def run(ctx, in_flight, learned, model):
    if not in_flight.strip():
        raise GuildError("--in-flight must not be empty", 1)
    if not learned.strip():
        raise GuildError("--learned must not be empty", 1)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    patterns = pii.project_patterns(ctx.projects_dir, binding["project"])
    pii.validate_field(in_flight, "--in-flight", pii.HANDOFF_FIELD_MAX_LENGTH, patterns)
    pii.validate_field(learned, "--learned", pii.HANDOFF_FIELD_MAX_LENGTH, patterns)
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
            {"party": party, "generation": generation, "handoff_path": str(handoff_path)},
        )
    return "{}\n{}".format(_resume_command(party, generation + 1, model), pii.BROADCAST_REMINDER)
