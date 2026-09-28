import json
import os
import re
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
    return [handoff_content, ""] + next_commands.run(ctx, binding, False, False)


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
    message_lines, seq = inbox_commands.new_lines(ctx, binding)
    lines = inbox_commands.framed(message_lines)
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
    message_lines, seq = inbox_commands.new_lines(ctx, binding)
    lines = inbox_commands.framed(message_lines)
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


_UNRESOLVED_BRANCH_MESSAGE = "guild: could not determine the branch for this push; PR state not verified"
_PUSH_OPERATORS = ("&&", "||", ";")
_PUSH_WRAPPER_COMMANDS = ("env", "command", "sudo")
_PUSH_SHELL_C_INVOKERS = ("bash", "sh")
_ASSIGNMENT_TOKEN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _tokenize_command(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def _split_top_level_segments(tokens):
    segments = []
    current = []
    for token in tokens:
        if token in _PUSH_OPERATORS:
            if current:
                segments.append(current)
            current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments


def _strip_wrapper_prefix(tokens):
    while tokens and _ASSIGNMENT_TOKEN_RE.match(tokens[0]):
        tokens = tokens[1:]
    while tokens and Path(tokens[0]).name in _PUSH_WRAPPER_COMMANDS:
        tokens = tokens[1:]
        while tokens and _ASSIGNMENT_TOKEN_RE.match(tokens[0]):
            tokens = tokens[1:]
    return tokens


def _shell_c_inner_command(tokens):
    if len(tokens) < 3:
        return None
    if Path(tokens[0]).name not in _PUSH_SHELL_C_INVOKERS or tokens[1] != "-c":
        return None
    return tokens[2]


def _push_segments(command):
    segments = []
    for raw_segment in _split_top_level_segments(_tokenize_command(command)):
        stripped = _strip_wrapper_prefix(raw_segment)
        inner_command = _shell_c_inner_command(stripped)
        if inner_command is not None:
            segments.extend(_push_segments(inner_command))
            continue
        segments.append(stripped)
    return segments


def _strip_ref_prefix(ref):
    prefix = "refs/heads/"
    if ref.startswith(prefix):
        return ref[len(prefix):]
    return ref


def _current_branch(cwd):
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"], cwd=str(cwd), capture_output=True, text=True
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _git_global_options(tokens, default_cwd):
    target_dir = default_cwd
    remaining = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "-C" and index + 1 < len(tokens):
            target_dir = tokens[index + 1]
            index += 2
            continue
        if token == "-c" and index + 1 < len(tokens):
            index += 2
            continue
        if token.startswith("--git-dir="):
            index += 1
            continue
        remaining.append(token)
        index += 1
    return target_dir, remaining


def _push_invocation(tokens, default_cwd):
    if not tokens or Path(tokens[0]).name != "git":
        return None
    target_dir, remaining = _git_global_options(tokens[1:], default_cwd)
    if not remaining or remaining[0] != "push":
        return None
    return target_dir, remaining[1:]


def _resolve_push_branch(push_args, target_dir):
    non_flag = [tok for tok in push_args if not tok.startswith("-")]
    if len(non_flag) >= 2:
        refspec = non_flag[1]
        source = refspec.split(":", 1)[0]
        return _current_branch(target_dir) if source == "HEAD" else _strip_ref_prefix(source)
    return _current_branch(target_dir)


def _unresolved_branch_result():
    return {"blocked": False, "message": None, "system_message": _UNRESOLVED_BRANCH_MESSAGE}


def pre_push(command, cwd):
    try:
        segments = _push_segments(command)
    except ValueError:
        return _unresolved_branch_result()
    for tokens in segments:
        invocation = _push_invocation(tokens, cwd)
        if invocation is None:
            continue
        target_dir, push_args = invocation
        if not Path(target_dir).is_dir():
            return _unresolved_branch_result()
        branch = _resolve_push_branch(push_args, target_dir)
        if not branch:
            return _unresolved_branch_result()
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
