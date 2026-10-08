import fnmatch
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from guild import config, ctx_pressure, db, identity, localbase, names, session_status, timeutil, tmux_windows
from guild.adapters import github
from guild.commands import brief as brief_commands
from guild.commands import claim as claim_commands
from guild.commands import inbox as inbox_commands
from guild.commands import next as next_commands
from guild.commands import party as party_commands
from guild.commands import raid as raid_commands
from guild.commands import statusline as statusline_commands
from guild.commands import task_brief
from guild.errors import GuildError
from guild.identity import UNBOUND_HINT

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EDIT_TOOL_PATH_FIELDS = {
    "Edit": "file_path",
    "Write": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}


_ISOLATED_LAUNCHER = (
    "import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); sys.argv[0] = 'guild'; "
    "runpy.run_module('guild', run_name='__main__', alter_sys=True)"
)


def _spawn_background_sync(cwd):
    subprocess.Popen(
        [sys.executable, "-I", "-c", _ISOLATED_LAUNCHER, str(_REPO_ROOT), "sync", "--source", "gh"],
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _resume_marker_path(ctx, generation):
    return ctx.state_dir / "hints" / "resumed-{}-g{}".format(identity.cursor_key(ctx.session_id), generation)


def _touch_marker(marker):
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()


def _resume_lines(ctx, binding):
    if binding["generation"] <= 1:
        return []
    marker = _resume_marker_path(ctx, binding["generation"])
    if marker.exists():
        return []
    failure_lines = []
    try:
        brief_lines = task_brief.render_for_binding(ctx, binding)
    except Exception as error:
        brief_lines = []
        failure_lines = ["guild: task brief unavailable ({})".format(type(error).__name__)]
    if brief_lines:
        _touch_marker(marker)
        return brief_lines + [""] + next_commands.run(ctx, binding, False, False)
    handoff_content = party_commands.previous_handoff_content(
        ctx.conn, binding["party"], binding["generation"]
    )
    if handoff_content is None:
        return failure_lines
    _touch_marker(marker)
    return [handoff_content, ""] + next_commands.run(ctx, binding, False, False) + failure_lines


def _auto_resume_lines(ctx, resume_party, permission_mode):
    if resume_party is None:
        return []
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    if binding is not None and binding["party"] == resume_party:
        return []
    label = "GUILD_RESUME={} not applied".format(resume_party)
    try:
        names.validate_name(resume_party, "party name")
    except GuildError as error:
        return ["{}: {}".format(label, error.message)]
    row = ctx.conn.execute("SELECT state FROM parties WHERE name = ?", (resume_party,)).fetchone()
    if row is None:
        return ["{}: unknown party".format(label)]
    if row["state"] != "awaiting-leader":
        return ["{}: party is {}".format(label, row["state"])]
    return [party_commands.resume(ctx, resume_party, None, permission_mode).splitlines()[0]]


def _membership_warning_marker_path(ctx, raid_name, expires_at):
    digest = hashlib.sha256("{}|{}".format(raid_name, expires_at).encode()).hexdigest()[:16]
    return ctx.state_dir / "hints" / "raid-warn-{}-{}".format(identity.cursor_key(ctx.session_id), digest)


def _membership_warning_lines(ctx, binding):
    if binding is None:
        return []
    lines = []
    for row in raid_commands.member_raids(ctx.conn, ctx.now, binding["party"]):
        if row["expires_at"] is None:
            continue
        remaining = timeutil.from_iso(row["expires_at"]) - ctx.now
        if remaining > timeutil.MEMBERSHIP_WARNING_WINDOW:
            continue
        marker = _membership_warning_marker_path(ctx, row["raid"], row["expires_at"])
        if marker.exists():
            continue
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        lines.append(
            "guild: raid {} membership expires in {}h"
            " — renew with guild raid join {} --ttl <dur> or --until-leave".format(
                row["raid"], timeutil.hours_until(ctx.now, row["expires_at"]), row["raid"]
            )
        )
    return lines


def _pause_marker_path(ctx, raid_name, paused_at):
    digest = hashlib.sha256("{}|{}".format(raid_name, paused_at).encode()).hexdigest()[:16]
    return ctx.state_dir / "hints" / "raid-pause-{}-{}".format(identity.cursor_key(ctx.session_id), digest)


def _pause_lines(ctx, binding):
    if binding is None:
        return []
    lines = []
    for row in raid_commands.paused_member_raids(ctx.conn, ctx.now, binding["party"]):
        marker = _pause_marker_path(ctx, row["raid"], row["paused_at"])
        if marker.exists():
            continue
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        lines.append("raid {} paused: finish current step and leave guild handoff".format(row["raid"]))
    return lines


_NOTIFICATION_WAITS = {
    "permission_prompt": ("permission", "waiting-permission"),
    "elicitation_dialog": ("elicitation", "waiting-input"),
    "idle_prompt": ("idle", "waiting-input"),
}


def _mark_working(ctx, binding):
    if binding is None:
        return
    if not session_status.is_change(ctx.conn, ctx.session_id, "working"):
        return
    session_status.record_change(ctx, binding, "session.working", {})


def stop(ctx):
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    if binding is None:
        return
    with db.writing(ctx.conn):
        if not session_status.is_change(ctx.conn, ctx.session_id, "stopped"):
            return
        session_status.record_change(ctx, binding, "session.stopped", {})


_BLOCKING_WAITS = ("permission", "elicitation")


def _hides_pending_permission(wait, previous_row):
    return wait == "idle" and previous_row is not None and previous_row["status"] == "waiting-permission"


def _run_push(ctx, binding, wait, push_runner):
    if binding["project"] is None:
        return
    notify_config = config.load_project(ctx.projects_dir, binding["project"]).get("notify")
    if notify_config is None:
        return
    try:
        push_runner(notify_config["command"] + [binding["party"], wait])
    except OSError as error:
        sys.stderr.write("guild: notify command failed: {}\n".format(error))


def notification(ctx, notification_type, message, push_runner):
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    if binding is None:
        return
    mapped = _NOTIFICATION_WAITS.get(notification_type)
    if mapped is None:
        return
    wait, status = mapped
    with db.writing(ctx.conn):
        previous_row = session_status.current(ctx.conn, ctx.session_id)
        if _hides_pending_permission(wait, previous_row):
            return
        if not session_status.is_change(ctx.conn, ctx.session_id, status):
            return
        session_status.record_change(
            ctx, binding, "session.waiting", session_status.waiting_payload(wait, message)
        )
    if wait not in _BLOCKING_WAITS:
        return
    _run_push(ctx, binding, wait, push_runner)


def session_start(ctx, resume_party, permission_mode):
    lines = _auto_resume_lines(ctx, resume_party, permission_mode)
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    if binding is not None:
        party_commands.locate_if_changed(ctx, binding, permission_mode)
        lines.extend(_resume_lines(ctx, binding))
        with db.writing(ctx.conn):
            _mark_working(ctx, binding)
    lines.extend(brief_commands.render_brief(ctx))
    lines.extend(_membership_warning_lines(ctx, binding))
    _spawn_background_sync(ctx.cwd)
    return "\n".join(lines)


def _hint_marker_path(ctx):
    return ctx.state_dir / "hints" / identity.cursor_key(ctx.session_id)


def _nudge_marker_path(ctx):
    return ctx.state_dir / "hints" / "nudge-{}".format(identity.cursor_key(ctx.session_id))


def _can_respawn(conn, binding):
    if party_commands.is_keeper(conn, binding["party"]):
        return True
    return tmux_windows.recorded_window(conn, binding["party"], binding["generation"]) is not None


def _ctx_nudge_lines(ctx, binding):
    if binding is None or binding["project"] is None:
        return []
    project = binding["project"]
    pct = statusline_commands.read_ctx(ctx.state_dir, ctx.session_id)
    if pct is None:
        return []
    project_data = config.load_project(ctx.projects_dir, project)
    if not ctx_pressure.is_high(pct, project_data):
        return []
    marker = _nudge_marker_path(ctx)
    if marker.exists():
        return []
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    if _can_respawn(ctx.conn, binding):
        return [
            "Context at {}%. Start nothing new; let in-flight runs finish, then run "
            '`guild handoff --respawn --in-flight "..." --learned "..."`. Nothing after it.'.format(pct)
        ]
    return [
        "Context at {}%. Start nothing new; let in-flight runs finish, then run "
        '`guild handoff --in-flight "..." --learned "..."`. '
        "Give the human the printed command, then nothing.".format(pct)
    ]


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
    lines = (
        lines
        + _ctx_nudge_lines(ctx, binding)
        + _membership_warning_lines(ctx, binding)
        + _pause_lines(ctx, binding)
    )
    with db.writing(ctx.conn):
        inbox_commands.advance_cursor(ctx.conn, identity.cursor_key(ctx.session_id), seq)
        _mark_working(ctx, binding)
    return "\n".join(lines)


def post_tool_use(ctx):
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    message_lines, seq = inbox_commands.new_lines(ctx, binding)
    lines = inbox_commands.framed(message_lines)
    lines = (
        lines
        + _ctx_nudge_lines(ctx, binding)
        + _membership_warning_lines(ctx, binding)
        + _pause_lines(ctx, binding)
    )
    with db.writing(ctx.conn):
        inbox_commands.advance_cursor(ctx.conn, identity.cursor_key(ctx.session_id), seq)
        _mark_working(ctx, binding)
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


def _is_delete_push(push_args):
    if "--delete" in push_args or "-d" in push_args:
        return True
    refspecs = [tok for tok in push_args if not tok.startswith("-")][1:]
    return any(refspec.startswith(":") for refspec in refspecs)


def _resolve_push_branch(push_args, target_dir):
    non_flag = [tok for tok in push_args if not tok.startswith("-")]
    if len(non_flag) >= 2:
        refspec = non_flag[1]
        source = refspec.split(":", 1)[0]
        return _current_branch(target_dir) if source == "HEAD" else _strip_ref_prefix(source)
    return _current_branch(target_dir)


def _push_diff_paths(target_dir, base_ref):
    try:
        result = subprocess.run(
            ["git", "-C", str(target_dir), "diff", "--name-only", "{}...HEAD".format(base_ref)],
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line]


def _shared_areas_push_result(ctx, target_dir):
    base_ref = localbase.origin_head_ref(target_dir)
    if base_ref is None:
        return {
            "blocked": False,
            "message": None,
            "system_message": "guild: could not determine base branch; shared_areas not checked",
        }
    paths = _push_diff_paths(target_dir, base_ref)
    if paths is None:
        return {
            "blocked": False,
            "message": None,
            "system_message": "guild: could not diff against {}; shared_areas not checked".format(base_ref),
        }
    reasons = _claim_shared_areas_or_reasons(ctx.with_cwd(Path(target_dir)), paths)
    if not reasons:
        return None
    return {"blocked": True, "message": "\n".join(reasons), "system_message": None}


def _unresolved_branch_result():
    return {"blocked": False, "message": None, "system_message": _UNRESOLVED_BRANCH_MESSAGE}


def pre_push(ctx, command):
    try:
        segments = _push_segments(command)
    except ValueError:
        return _unresolved_branch_result()
    for tokens in segments:
        invocation = _push_invocation(tokens, ctx.cwd)
        if invocation is None:
            continue
        target_dir, push_args = invocation
        if _is_delete_push(push_args):
            continue
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
        shared_areas_result = _shared_areas_push_result(ctx, target_dir)
        if shared_areas_result is not None:
            return shared_areas_result
    return {"blocked": False, "message": None, "system_message": None}


_GIT_WRITE_VERBS = ("push", "rebase", "commit")
_GH_PR_WRITE_VERBS = ("checkout", "comment", "review", "edit", "ready", "close", "merge")
_GH_PR_VALUE_FLAGS = ("-R", "--repo", "-b", "--body", "-F", "--body-file", "-t", "--title", "-B", "--base")
_GH_REPO_FLAGS = ("-R", "--repo")
_PR_NUMBER_RE = re.compile(r"^\d+$")
_PR_URL_RE = re.compile(r"github\.com/([^/]+/[^/]+)/pull/(\d+)")


def _git_pr_target(tokens, default_cwd):
    if not tokens or Path(tokens[0]).name != "git":
        return None
    target_dir, remaining = _git_global_options(tokens[1:], default_cwd)
    if not remaining or remaining[0] not in _GIT_WRITE_VERBS:
        return None
    if remaining[0] == "push":
        if _is_delete_push(remaining[1:]):
            return None
        branch = _resolve_push_branch(remaining[1:], target_dir)
    else:
        branch = _current_branch(target_dir)
    if not branch:
        return None
    return {"repo": localbase.origin_repo_slug(target_dir), "number": None, "branch": branch}


def _gh_pr_arguments(args):
    repo = None
    positional = None
    index = 0
    while index < len(args):
        token = args[index]
        if token in _GH_PR_VALUE_FLAGS:
            if token in _GH_REPO_FLAGS and index + 1 < len(args):
                repo = args[index + 1]
            index += 2
            continue
        if not token.startswith("-") and positional is None:
            positional = token
        index += 1
    return repo, positional


def _gh_pr_target(tokens, default_cwd):
    if len(tokens) < 3 or Path(tokens[0]).name != "gh":
        return None
    if tokens[1] != "pr" or tokens[2] not in _GH_PR_WRITE_VERBS:
        return None
    repo, positional = _gh_pr_arguments(tokens[3:])
    if repo is None:
        repo = localbase.origin_repo_slug(default_cwd)
    if positional is None:
        return {"repo": repo, "number": None, "branch": _current_branch(default_cwd)}
    if _PR_NUMBER_RE.match(positional):
        return {"repo": repo, "number": int(positional), "branch": None}
    url_match = _PR_URL_RE.search(positional)
    if url_match:
        return {"repo": url_match.group(1), "number": int(url_match.group(2)), "branch": None}
    return {"repo": repo, "number": None, "branch": positional}


def _pr_target(tokens, default_cwd):
    git_target = _git_pr_target(tokens, default_cwd)
    if git_target is not None:
        return git_target
    return _gh_pr_target(tokens, default_cwd)


def _foreign_pr(ctx, binding, target):
    if target["number"] is None and not target["branch"]:
        return None
    if target["number"] is not None and target["repo"] is None:
        return None
    return ctx.conn.execute(
        "SELECT repo, number, party FROM prs"
        " WHERE party != ? AND COALESCE(gh_state, 'OPEN') = 'OPEN'"
        " AND (? IS NULL OR repo = ?) AND (? IS NULL OR number = ?) AND (? IS NULL OR branch = ?)"
        " ORDER BY repo, number LIMIT 1",
        (
            binding["party"],
            target["repo"], target["repo"],
            target["number"], target["number"],
            target["branch"], target["branch"],
        ),
    ).fetchone()


def _foreign_pr_confirmation(binding, row):
    reason = "guild: {}#{} belongs to party '{}'; this session is party '{}' — confirm before touching it".format(
        row["repo"], row["number"], row["party"], binding["party"]
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }


def pre_pr_owner(ctx, command):
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    if binding is None:
        return None
    try:
        segments = _push_segments(command)
    except ValueError:
        return None
    for tokens in segments:
        target = _pr_target(tokens, ctx.cwd)
        if target is None:
            continue
        row = _foreign_pr(ctx, binding, target)
        if row is not None:
            return _foreign_pr_confirmation(binding, row)
    return None


def _edit_file_path(tool_name, tool_input):
    field = _EDIT_TOOL_PATH_FIELDS.get(tool_name)
    if field is None:
        return None
    return tool_input.get(field) or None


def _first_existing_ancestor(path):
    current = path.parent
    while not current.exists():
        parent = current.parent
        if parent == current:
            return current
        current = parent
    return current


def _git_toplevel(file_path):
    start_dir = _first_existing_ancestor(Path(file_path))
    try:
        result = subprocess.run(
            ["git", "-C", str(start_dir), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _relative_posix_path(file_path, toplevel):
    return os.path.relpath(str(file_path), toplevel).replace(os.sep, "/")


def _matching_shared_area(relative_path, shared_areas):
    for pattern in shared_areas:
        if fnmatch.fnmatch(relative_path, pattern):
            return pattern
    return None


def _shared_area_deny_reason(ctx, binding, holder_party, holder_expires_at, matched_glob):
    local_time = timeutil.from_iso(holder_expires_at).astimezone().strftime("%H:%M")
    caller_raids = raid_commands.member_raid_names(ctx.conn, ctx.now, binding["party"])
    holder_raids = raid_commands.member_raid_names(ctx.conn, ctx.now, holder_party)
    shared_raids = set(caller_raids) & set(holder_raids)
    if shared_raids:
        raid_name = sorted(shared_raids)[0]
        coordination = "coordinate in the raid (guild notice --to raid:{}) or wait".format(raid_name)
    else:
        coordination = "coordinate with party '{}' or wait".format(holder_party)
    return "guild: '{}' is claimed by party '{}' until {} — {}".format(
        matched_glob, holder_party, local_time, coordination
    )


def _foreign_holder_reason(ctx, binding, project, matched_glob):
    row = ctx.conn.execute(
        "SELECT party, expires_at FROM claims WHERE project = ? AND area = ?",
        (project, "area:{}".format(matched_glob)),
    ).fetchone()
    if row is None or timeutil.is_expired(ctx.now, row["expires_at"]) or row["party"] == binding["party"]:
        return None
    return _shared_area_deny_reason(ctx, binding, row["party"], row["expires_at"], matched_glob)


def _claim_shared_area_or_deny(ctx, binding, project, project_data, matched_glob, agent_type):
    reason = _foreign_holder_reason(ctx, binding, project, matched_glob)
    if reason is not None:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    claim_commands.claim(ctx, "area:{}".format(matched_glob), project_data["shared_area_claim_ttl"], agent_type)
    return None


def pre_edit(ctx, tool_name, tool_input, agent_type):
    file_path = _edit_file_path(tool_name, tool_input)
    if file_path is None:
        return None
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    if binding is None:
        return None
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    if project is None:
        return None
    project_data = config.load_project(ctx.projects_dir, project)
    shared_areas = project_data.get("shared_areas")
    if not shared_areas:
        return None
    toplevel = _git_toplevel(file_path)
    if toplevel is None:
        return None
    relative_path = _relative_posix_path(file_path, toplevel)
    matched_glob = _matching_shared_area(relative_path, shared_areas)
    if matched_glob is None:
        return None
    return _claim_shared_area_or_deny(ctx, binding, project, project_data, matched_glob, agent_type)


def staged_paths(cwd):
    result = subprocess.run(
        ["git", "-C", str(cwd), "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line]


def _claim_shared_areas_or_reasons(ctx, paths):
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    if binding is None:
        return []
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    if project is None:
        return []
    project_data = config.load_project(ctx.projects_dir, project)
    shared_areas = project_data.get("shared_areas")
    if not shared_areas:
        return []
    matched_globs = sorted({glob for glob in (_matching_shared_area(path, shared_areas) for path in paths) if glob})
    reasons = [
        reason
        for reason in (_foreign_holder_reason(ctx, binding, project, glob) for glob in matched_globs)
        if reason is not None
    ]
    if reasons:
        return reasons
    for glob in matched_globs:
        claim_commands.claim(ctx, "area:{}".format(glob), project_data["shared_area_claim_ttl"], None)
    return []


def pre_commit(ctx, paths_in_commit):
    return _claim_shared_areas_or_reasons(ctx, paths_in_commit)
