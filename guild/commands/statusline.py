from guild import identity, names, session_status
from guild.commands import notice as notice_commands
from guild.commands import raid as raid_commands


def record_ctx(state_dir, session_id, pct):
    directory = state_dir / "ctx"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / names.safe_key(session_id)).write_text(str(pct))


def record_baseline_once(state_dir, session_id, pct):
    path = state_dir / "ctx-baseline" / names.safe_key(session_id)
    if pct == 0 or path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pct))


def read_ctx(state_dir, session_id):
    return _read_pct(state_dir / "ctx" / names.safe_key(session_id))


def ctx_recorded_at(state_dir, session_id):
    return (state_dir / "ctx" / names.safe_key(session_id)).stat().st_mtime


def read_baseline(state_dir, session_id):
    return _read_pct(state_dir / "ctx-baseline" / names.safe_key(session_id))


def latest_baseline(state_dir):
    directory = state_dir / "ctx-baseline"
    if not directory.is_dir():
        return None
    files = sorted(directory.iterdir(), key=lambda path: path.stat().st_mtime)
    if not files:
        return None
    return _read_pct(files[-1])


def _read_pct(path):
    if not path.is_file():
        return None
    try:
        return int(path.read_text().strip())
    except ValueError:
        return None


def record_compact_pct(state_dir, pct):
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / "compaction-pct").open("a") as handle:
        handle.write("{}\n".format(pct))


def latest_compact_pct(state_dir):
    path = state_dir / "compaction-pct"
    if not path.is_file():
        return None
    samples = [int(line) for line in path.read_text().split() if line.isdigit()]
    if not samples:
        return None
    return samples[-1]


def _raid_label(ctx, row):
    if raid_commands.is_paused(ctx.conn, row["raid"]):
        return "{} ⏸".format(row["raid"])
    return row["raid"]


def _identity_parts(ctx, party, generation):
    raids = sorted(raid_commands.member_raids(ctx.conn, ctx.now, party), key=lambda row: row["raid"])
    parts = []
    if raids:
        parts.append("⚔ " + ", ".join(_raid_label(ctx, row) for row in raids))
    parts.append("g{}".format(generation))
    return parts


def render(ctx, session_id):
    binding = identity.resolve_binding(ctx.conn, session_id)
    project = binding["project"] if binding is not None else None
    party = binding["party"] if binding is not None else None
    total_open_asks = ctx.conn.execute("SELECT COUNT(*) AS n FROM asks WHERE state = 'open'").fetchone()["n"]
    active = notice_commands.active_notices(ctx.conn, ctx.now)
    raid_member_of = raid_commands.member_raid_names(ctx.conn, ctx.now, party)
    targeting = notice_commands.targeting(active, project, True, raid_member_of)
    parts = []
    if party is not None:
        parts.extend(_identity_parts(ctx, party, binding["generation"]))
    if total_open_asks:
        parts.append("⚑{} asks".format(total_open_asks))
    if targeting:
        noun = "notice" if len(targeting) == 1 else "notices"
        parts.append("{} {}".format(len(targeting), noun))
    blocked = len(session_status.blocked_rows(ctx.conn, None))
    if blocked:
        parts.append("⏸{} blocked".format(blocked))
    return " · ".join(parts)
