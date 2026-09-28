import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from guild import config, db, identity
from guild.adapters import github
from guild.commands import brief as brief_commands
from guild.commands import inbox as inbox_commands
from guild.commands import next as next_commands
from guild.commands import party as party_commands
from guild.commands import statusline as statusline_commands
from guild.identity import UNBOUND_HINT

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _spawn_background_sync(cwd):
    env = dict(os.environ)
    existing_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(_REPO_ROOT) if not existing_path else "{}:{}".format(_REPO_ROOT, existing_path)
    subprocess.Popen(
        [sys.executable, "-m", "guild", "sync", "--source", "gh"],
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _resume_marker_path(ctx, generation):
    return ctx.state_dir / "hints" / "resumed-{}-g{}".format(identity.cursor_key(ctx.session_id), generation)


def _resume_lines(ctx, binding):
    if binding["generation"] <= 1:
        return []
    marker = _resume_marker_path(ctx, binding["generation"])
    if marker.exists():
        return []
    handoff_content = party_commands.previous_handoff_content(
        ctx.conn, binding["party"], binding["generation"]
    )
    if handoff_content is None:
        return []
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    return [handoff_content, ""] + next_commands.run(ctx, False, False)


def session_start(ctx):
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    lines = []
    if binding is not None:
        lines = _resume_lines(ctx, binding)
    lines.extend(brief_commands.render_brief(ctx))
    _spawn_background_sync(ctx.cwd)
    return "\n".join(lines)


def _hint_marker_path(ctx):
    return ctx.state_dir / "hints" / identity.cursor_key(ctx.session_id)


def _nudge_marker_path(ctx):
    return ctx.state_dir / "hints" / "nudge-{}".format(identity.cursor_key(ctx.session_id))


def _ctx_nudge_lines(ctx, project):
    if project is None:
        return []
    pct = statusline_commands.read_ctx(ctx.state_dir, ctx.session_id)
    if pct is None:
        return []
    project_data = config.load_project(ctx.projects_dir, project)
    threshold = project_data.get("handoff_threshold")
    if threshold is None or pct < threshold:
        return []
    marker = _nudge_marker_path(ctx)
    if marker.exists():
        return []
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    return ["Context at {}%. Finish current step, run `guild handoff`.".format(pct)]


def prompt_submit(ctx):
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    lines, seq = inbox_commands.new_lines(ctx, binding)
    if binding is None:
        marker = _hint_marker_path(ctx)
        if not marker.exists():
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
            lines = [UNBOUND_HINT] + lines
    project = binding["project"] if binding is not None else None
    lines = lines + _ctx_nudge_lines(ctx, project)
    with db.writing(ctx.conn):
        inbox_commands.advance_cursor(ctx.conn, identity.cursor_key(ctx.session_id), seq)
    return "\n".join(lines)


def post_tool_use(ctx):
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    lines, seq = inbox_commands.new_lines(ctx, binding)
    project = binding["project"] if binding is not None else None
    lines = lines + _ctx_nudge_lines(ctx, project)
    with db.writing(ctx.conn):
        inbox_commands.advance_cursor(ctx.conn, identity.cursor_key(ctx.session_id), seq)
    if not lines:
        return None
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": "\n".join(lines),
            }
        }
    )


def _push_segments(command):
    segments = []
    for chunk in command.replace(";", "&&").split("&&"):
        try:
            tokens = shlex.split(chunk.strip())
        except ValueError:
            continue
        segments.append(tokens)
    return segments


def _strip_ref_prefix(ref):
    prefix = "refs/heads/"
    if ref.startswith(prefix):
        return ref[len(prefix):]
    return ref


def _current_branch(cwd):
    result = subprocess.run(
        ["git", "branch", "--show-current"], cwd=str(cwd), capture_output=True, text=True
    )
    return result.stdout.strip()


def _resolve_push_target(tokens, default_cwd):
    target_dir = default_cwd
    remaining = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "-C" and index + 1 < len(tokens):
            target_dir = tokens[index + 1]
            index += 2
            continue
        remaining.append(token)
        index += 1
    if "push" not in remaining:
        return None
    push_index = remaining.index("push")
    non_flag = [tok for tok in remaining[push_index + 1:] if not tok.startswith("-")]
    if len(non_flag) >= 2:
        refspec = non_flag[1]
        source = refspec.split(":", 1)[0]
        branch = _current_branch(target_dir) if source == "HEAD" else _strip_ref_prefix(source)
    else:
        branch = _current_branch(target_dir)
    return target_dir, branch


def pre_push(command, cwd):
    for tokens in _push_segments(command):
        if not tokens or tokens[0] != "git":
            continue
        resolved = _resolve_push_target(tokens, cwd)
        if resolved is None:
            continue
        target_dir, branch = resolved
        try:
            prs = github.pr_list_for_branch(target_dir, branch, ["number", "state", "url"])
        except github.GhCommandError as error:
            return {
                "blocked": False,
                "message": None,
                "system_message": "guild: could not verify PR state for {}: {}".format(branch, error),
            }
        has_open = any(pr["state"] == "OPEN" for pr in prs)
        has_closed_or_merged = any(pr["state"] in ("MERGED", "CLOSED") for pr in prs)
        if not has_open and has_closed_or_merged:
            merged_or_closed = next(pr for pr in prs if pr["state"] in ("MERGED", "CLOSED"))
            return {
                "blocked": True,
                "message": "guild: branch {} belongs to merged/closed PR #{}; open a new branch/PR".format(
                    branch, merged_or_closed["number"]
                ),
                "system_message": None,
            }
    return {"blocked": False, "message": None, "system_message": None}
