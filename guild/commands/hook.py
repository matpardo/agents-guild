import fnmatch
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from guild import (
    background,
    config,
    ctx_pressure,
    db,
    due_jobs,
    identity,
    localbase,
    names,
    paths,
    session_status,
    timeutil,
    tmux_windows,
)
from guild.adapters import github
from guild.commands import adventurer as adventurer_commands
from guild.commands import brief as brief_commands
from guild.commands import claim as claim_commands
from guild.commands import inbox as inbox_commands
from guild.commands import memory as memory_commands
from guild.commands import merge_queue as merge_queue_commands
from guild.commands import next as next_commands
from guild.commands import party as party_commands
from guild.commands import raid as raid_commands
from guild.commands import statusline as statusline_commands
from guild.commands import task_brief
from guild.errors import GuildError
from guild.identity import UNBOUND_HINT

_IDLE_COMPACTION_SECONDS = 30 * 60
_EDIT_TOOL_PATH_FIELDS = {
    "Edit": "file_path",
    "Write": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}


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
    memory_lines = memory_commands.framed_memory(binding["party"])
    failure_lines = []
    try:
        brief_lines = task_brief.render_for_binding(ctx, binding)
    except Exception as error:
        brief_lines = []
        failure_lines = ["guild: task brief unavailable ({})".format(type(error).__name__)]
    if brief_lines:
        _touch_marker(marker)
        lines = brief_lines + [""] + next_commands.run(ctx, binding, False, False)
        return lines + [""] + memory_lines if memory_lines else lines
    handoff_content = party_commands.previous_handoff_content(ctx.conn, binding["party"], binding["generation"])
    if handoff_content is None:
        return failure_lines
    _touch_marker(marker)
    lines = (
        party_commands.framed_handoff(handoff_content)
        + [""]
        + next_commands.run(ctx, binding, False, False)
        + failure_lines
    )
    return lines + [""] + memory_lines if memory_lines else lines


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


def _auto_adventurer_lines(ctx, health_job, source):
    if health_job is None or source != "startup":
        return []
    if identity.resolve_binding(ctx.conn, ctx.session_id) is not None:
        return []
    if identity.resolve_adventurer(ctx.conn, ctx.session_id) is not None:
        return []
    try:
        return [
            adventurer_commands.start(
                ctx, None, None, health_job, "health job {} launched by the human".format(health_job)
            )
        ]
    except GuildError as error:
        return ["GUILD_ADVENTURER_JOB={} not applied: {}".format(health_job, error.message)]


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
    "elicitation_dialog": ("elicitation", "waiting-permission"),
    "idle_prompt": ("idle", "waiting-input"),
}


def _session_actor(ctx):
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    if binding is not None:
        return binding
    adventurer = identity.resolve_adventurer(ctx.conn, ctx.session_id)
    if adventurer is None:
        return None
    return {"party": None, "project": adventurer["project"]}


def _mark_working(ctx, binding):
    if binding is None:
        return
    if not session_status.is_change(ctx.conn, ctx.session_id, "working"):
        return
    session_status.record_change(ctx, binding, "session.working", {})


def _spawn_due_jobs(ctx):
    due_jobs.spawn_due(ctx.state_dir, ctx.cwd, time.time(), due_jobs.spawn_detached)


def stop(ctx):
    _spawn_due_jobs(ctx)
    binding = _session_actor(ctx)
    if binding is None:
        return
    with db.writing(ctx.conn):
        if not session_status.is_change(ctx.conn, ctx.session_id, "stopped"):
            return
        session_status.record_change(ctx, binding, "session.stopped", {})


def _subagent_meta_path(transcript_path, agent_id):
    if not transcript_path:
        return ""
    return str(
        Path(transcript_path).with_suffix("") / "subagents" / "agent-{}.meta.json".format(names.safe_key(agent_id))
    )


def subagent_start(ctx, agent_id, transcript_path):
    if agent_id is None or _session_actor(ctx) is None:
        return
    meta_path = _subagent_meta_path(transcript_path, agent_id)
    background.mark(ctx.state_dir, ctx.session_id, background.subagent_key(agent_id), meta_path)


def subagent_stop(ctx, agent_id):
    if agent_id is None or _session_actor(ctx) is None:
        return
    background.clear(ctx.state_dir, ctx.session_id, background.subagent_key(agent_id))


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
        session_status.record_change(ctx, binding, "session.waiting", session_status.waiting_payload(wait, message))
    if wait not in _BLOCKING_WAITS:
        return
    _run_push(ctx, binding, wait, push_runner)


def session_start(ctx, resume_party, health_job, permission_mode, source):
    if source in ("startup", "resume") and ctx.session_id is not None:
        background.clear_subagents(ctx.state_dir, ctx.session_id)
    lines = _auto_resume_lines(ctx, resume_party, permission_mode)
    lines.extend(_auto_adventurer_lines(ctx, health_job, source))
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    if binding is not None:
        party_commands.locate_if_changed(ctx, binding, permission_mode)
        lines.extend(_resume_lines(ctx, binding))
        with db.writing(ctx.conn):
            _mark_working(ctx, binding)
        lines.extend(_compact_nudge_lines(ctx, binding, source))
    lines.extend(brief_commands.render_brief(ctx))
    lines.extend(_membership_warning_lines(ctx, binding))
    _spawn_due_jobs(ctx)
    return "\n".join(lines)


def _hint_marker_path(ctx):
    return ctx.state_dir / "hints" / identity.cursor_key(ctx.session_id)


def _nudge_marker_path(ctx):
    return ctx.state_dir / "hints" / "nudge-{}".format(identity.cursor_key(ctx.session_id))


def _ctx_nudge_lines(ctx, binding):
    if binding is None or binding["project"] is None:
        return []
    project = binding["project"]
    project_data = config.load_project(ctx.projects_dir, project)
    global_config = config.load_global(paths.global_config_path())
    pressure = ctx_pressure.reading(ctx.state_dir, ctx.session_id, global_config, project_data)
    if pressure is None or not pressure["high"]:
        return []
    marker = _nudge_marker_path(ctx)
    if marker.exists():
        return []
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    return [_nudge_text(ctx, binding, "Context at {}%".format(pressure["pct"]))]


def _compact_nudge_lines(ctx, binding, source):
    if source != "compact" or binding["project"] is None:
        return []
    marker = _nudge_marker_path(ctx)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    return [_nudge_text(ctx, binding, "Context was compacted")]


def _idle_compaction(ctx):
    silence = ctx.now.timestamp() - statusline_commands.ctx_recorded_at(ctx.state_dir, ctx.session_id)
    return silence >= _IDLE_COMPACTION_SECONDS


def pre_compact(ctx):
    pct = statusline_commands.read_ctx(ctx.state_dir, ctx.session_id)
    if pct is None or _idle_compaction(ctx):
        return
    statusline_commands.record_compact_pct(ctx.state_dir, pct)


def _nudge_text(ctx, binding, lead):
    recorded_window = tmux_windows.recorded_window(ctx.conn, binding["party"], binding["generation"])
    if recorded_window is not None:
        return (
            "{}. Start nothing new; let in-flight runs finish, then run "
            '`guild handoff --respawn --in-flight "..." --learned "..."`. Nothing after it.'.format(lead)
        )
    return (
        "{}. Start nothing new; let in-flight runs finish, then run "
        '`guild handoff --in-flight "..." --learned "..."`. '
        "Give the human the printed command, then nothing.".format(lead)
    )


def prompt_submit(ctx):
    _spawn_due_jobs(ctx)
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    adventurer = identity.resolve_adventurer(ctx.conn, ctx.session_id)
    message_lines, seq = inbox_commands.new_lines(ctx, binding)
    lines = inbox_commands.framed(message_lines)
    if binding is None and adventurer is None:
        marker = _hint_marker_path(ctx)
        if not marker.exists():
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
            lines = [UNBOUND_HINT] + lines
    lines = (
        lines + _ctx_nudge_lines(ctx, binding) + _membership_warning_lines(ctx, binding) + _pause_lines(ctx, binding)
    )
    with db.writing(ctx.conn):
        inbox_commands.advance_cursor(ctx.conn, identity.cursor_key(ctx.session_id), seq)
        _mark_working(ctx, _session_actor(ctx))
    return "\n".join(lines)


def post_tool_use(ctx):
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    message_lines, seq = inbox_commands.new_lines(ctx, binding)
    lines = inbox_commands.framed(message_lines)
    lines = (
        lines + _ctx_nudge_lines(ctx, binding) + _membership_warning_lines(ctx, binding) + _pause_lines(ctx, binding)
    )
    with db.writing(ctx.conn):
        inbox_commands.advance_cursor(ctx.conn, identity.cursor_key(ctx.session_id), seq)
        _mark_working(ctx, _session_actor(ctx))
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
_GIT_VALUE_GLOBAL_OPTIONS = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env")
_ASSIGNMENT_TOKEN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _tokenize_command(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def _push_segments(command):
    return [tokens for tokens in _hook_segments(command) if tokens]


def _strip_ref_prefix(ref):
    prefix = "refs/heads/"
    if ref.startswith(prefix):
        return ref[len(prefix) :]
    return ref


def _current_branch(cwd):
    try:
        result = subprocess.run(["git", "branch", "--show-current"], cwd=str(cwd), capture_output=True, text=True)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _git_global_options(tokens, default_cwd):
    target_dir = default_cwd
    index = 0
    while index < len(tokens) and tokens[index].startswith("-"):
        token = tokens[index]
        takes_value = token in _GIT_VALUE_GLOBAL_OPTIONS
        if token == "-C" and index + 1 < len(tokens):
            target_dir = tokens[index + 1]
        index += 2 if takes_value else 1
    return target_dir, tokens[index:]


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


def _push_paths_or_result(target_dir):
    base_ref = localbase.origin_head_ref(target_dir)
    if base_ref is None:
        return None, {
            "blocked": False,
            "message": None,
            "system_message": "guild: could not determine base branch; shared_areas not checked",
        }
    paths = _push_diff_paths(target_dir, base_ref)
    if paths is None:
        return None, {
            "blocked": False,
            "message": None,
            "system_message": "guild: could not diff against {}; shared_areas not checked".format(base_ref),
        }
    return paths, None


def _file_cap_warning(ctx, target_dir, branch, paths):
    repo = localbase.origin_repo_slug(target_dir)
    if repo is None:
        return None
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    if project is None:
        return None
    project_data = config.load_project(ctx.projects_dir, project)
    cap = project_data.get("max_open_prs_per_file")
    if cap is None:
        return None
    external = merge_queue_commands.external_blocked_refs(ctx.conn)
    lines = []
    for path in sorted(paths):
        rows = merge_queue_commands.file_pr_rows(ctx.conn, external, repo, path, branch)
        if len(rows) >= cap:
            refs = ", ".join("{}#{} ({})".format(row["repo"], row["number"], row["party"]) for row in rows)
            lines.append("{}: {}".format(path, refs))
    if not lines:
        return None
    return "guild: open PRs already touch files of this push (cap {}); merge or rebase on those first\n{}".format(
        cap, "\n".join(lines)
    )


def _red_main_checks(ctx, repo):
    red = ctx.conn.execute(
        "SELECT source, reason, updated_at FROM main_status WHERE repo = ? AND red = 1 AND external IS NULL ORDER BY source",
        (repo,),
    ).fetchall()
    if not red:
        return None
    return "; ".join(
        "{} ({}, red since {})".format(row["reason"] or "no reason given", row["source"], row["updated_at"])
        for row in red
    )


def _fixes_main_pr_exists(ctx, repo, number, branch):
    if number is None and not branch:
        return False
    row = ctx.conn.execute(
        "SELECT 1 FROM prs WHERE repo = ? AND fixes_main = 1 AND lifecycle NOT IN ('merged', 'closed')"
        " AND (? IS NULL OR number = ?) AND (? IS NULL OR branch = ?)",
        (repo, number, number, branch, branch),
    ).fetchone()
    return row is not None


def _red_main_push_result(ctx, target_dir, branch, open_pr):
    repo = localbase.origin_repo_slug(target_dir)
    if repo is None:
        return None
    checks = _red_main_checks(ctx, repo)
    if checks is None:
        return None
    if _fixes_main_pr_exists(ctx, repo, None, branch):
        return None
    if open_pr is None or open_pr["isDraft"]:
        warning = "guild: main of {} is red: {}; keep iterating in draft, do not mark the PR Ready".format(repo, checks)
        return {"blocked": False, "message": None, "system_message": warning}
    message = (
        "guild: main of {} is red: {}\n"
        "pushing to Ready PR #{} would fire CI on red main: go back to draft with `gh pr ready --undo {}`,"
        " wait for main green, or flag it with `guild pr set <ref> --fixes-main` if it repairs main"
    ).format(repo, checks, open_pr["number"], open_pr["number"])
    return {"blocked": True, "message": message, "system_message": None}


def _flag_value(args, flags):
    for index, token in enumerate(args):
        if token in flags and index + 1 < len(args):
            return args[index + 1]
        for flag in flags:
            if flag.startswith("--") and token.startswith(flag + "="):
                return token[len(flag) + 1 :]
    return None


_CREATE_BOOLEAN_SHORT_FLAGS = frozenset("dfw")


def _creates_draft(args):
    for token in args:
        if token == "--draft":
            return True
        bundle = token[1:]
        if token.startswith("-") and not token.startswith("--") and "d" in bundle:
            if set(bundle) <= _CREATE_BOOLEAN_SHORT_FLAGS:
                return True
    return False


def _cd_destination(tokens, cwd):
    if not tokens or tokens[0] != "cd":
        return False, cwd
    if len(tokens) != 2 or tokens[1] == "-" or cwd is None:
        return True, None
    destination = Path(cwd) / Path(tokens[1]).expanduser()
    return True, destination if destination.is_dir() else None


def _needs_cwd(tokens):
    if _push_invocation(tokens, None) is not None:
        return True
    command = _gh_pr_command(tokens)
    return command is not None and command[1] in ("ready", "create")


def _gh_red_main_result(ctx, tokens, cwd):
    command = _gh_pr_command(tokens)
    if command is None:
        return None
    global_repo, verb, args = command
    if verb == "ready" and "--undo" not in args:
        target = _gh_pr_target(tokens, cwd)
        way_out = "keep the PR in draft (`gh pr ready --undo <n>`) and wait for main green"
    elif verb == "create" and not _creates_draft(args):
        repo, _ = _gh_pr_arguments(args)
        target = {
            "repo": repo or global_repo or localbase.origin_repo_slug(cwd),
            "number": None,
            "branch": _flag_value(args, ("-H", "--head")) or _current_branch(cwd),
        }
        way_out = "create it with `--draft` and wait for main green"
    else:
        return None
    if target["repo"] is None:
        return None
    checks = _red_main_checks(ctx, target["repo"])
    if checks is None:
        return None
    if _fixes_main_pr_exists(ctx, target["repo"], target["number"], target["branch"]):
        return None
    message = (
        "guild: main of {} is red: {}\n"
        "this PR would fire CI on red main: {}, or flag it with `guild pr set <ref> --fixes-main` if it repairs main"
    ).format(target["repo"], checks, way_out)
    return {"blocked": True, "message": message, "system_message": None}


def _billing_blocked_main_warning(ctx, target_dir):
    repo = localbase.origin_repo_slug(target_dir)
    if repo is None:
        return None
    blocked = ctx.conn.execute(
        "SELECT 1 FROM main_status WHERE repo = ? AND red = 1 AND external = 'billing'", (repo,)
    ).fetchone()
    if blocked is None:
        return None
    return "guild: main of {} is blocked by billing: CI will not run".format(repo)


def _shared_areas_push_result(ctx, target_dir, paths):
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
    warnings = []
    cwd = ctx.cwd
    for tokens in segments:
        is_cd, cwd = _cd_destination(tokens, cwd)
        if is_cd:
            continue
        if cwd is None and _needs_cwd(tokens):
            return _unresolved_branch_result()
        gh_result = _gh_red_main_result(ctx, tokens, cwd)
        if gh_result is not None:
            return gh_result
        invocation = _push_invocation(tokens, cwd)
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
            prs = github.pr_list_for_branch(target_dir, branch, ["number", "state", "url", "isDraft"])
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
        open_pr = next((pr for pr in prs if pr["state"] == "OPEN"), None)
        red_main_result = _red_main_push_result(ctx, target_dir, branch, open_pr)
        if red_main_result is not None and red_main_result["blocked"]:
            return red_main_result
        paths, failure = _push_paths_or_result(target_dir)
        if failure is not None:
            return failure
        shared_areas_result = _shared_areas_push_result(ctx, target_dir, paths)
        if shared_areas_result is not None:
            return shared_areas_result
        red_main_warning = None if red_main_result is None else red_main_result["system_message"]
        warnings.extend(
            warning
            for warning in (
                red_main_warning,
                _billing_blocked_main_warning(ctx, target_dir),
                _file_cap_warning(ctx.with_cwd(Path(target_dir)), target_dir, branch, paths),
            )
            if warning is not None
        )
    system_message = "\n".join(warnings) if warnings else None
    return {"blocked": False, "message": None, "system_message": system_message}


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
        if token.startswith("--repo="):
            repo = token[len("--repo=") :]
        if not token.startswith("-") and positional is None:
            positional = token
        index += 1
    return repo, positional


def _gh_pr_command(tokens):
    if len(tokens) < 3 or Path(tokens[0]).name != "gh":
        return None
    global_repo = None
    index = 1
    while index + 1 < len(tokens):
        if tokens[index] in _GH_REPO_FLAGS:
            global_repo = tokens[index + 1]
            index += 2
        elif tokens[index].startswith("--repo="):
            global_repo = tokens[index][len("--repo=") :]
            index += 1
        else:
            break
    if index + 1 >= len(tokens) or tokens[index] != "pr":
        return None
    return global_repo, tokens[index + 1], tokens[index + 2 :]


def _gh_pr_target(tokens, default_cwd):
    command = _gh_pr_command(tokens)
    if command is None:
        return None
    global_repo, verb, args = command
    if verb not in _GH_PR_WRITE_VERBS:
        return None
    repo, positional = _gh_pr_arguments(args)
    repo = repo or global_repo or localbase.origin_repo_slug(default_cwd)
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
            target["repo"],
            target["repo"],
            target["number"],
            target["number"],
            target["branch"],
            target["branch"],
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
    cwd = ctx.cwd
    for tokens in segments:
        is_cd, cwd = _cd_destination(tokens, cwd)
        if is_cd or cwd is None:
            continue
        target = _pr_target(tokens, cwd)
        if target is None:
            continue
        row = _foreign_pr(ctx, binding, target)
        if row is not None:
            return _foreign_pr_confirmation(binding, row)
    return None


_DENIED_ANSWER_SUBCOMMANDS = ("answer", "dismiss")
_ANSWER_DENY_REASON = "guild: agents cannot answer or dismiss an ask; only a human may run this outside a session"
_REALM_DENY_REASON = (
    "guild: agents cannot run realm commands other than status and doctor; only a human may run this outside a session"
)
_PYTHON_RE = re.compile(r"python(3(\.\d+)?)?")
_GUILD_MODULES = ("guild", "guild.cli")
_REALM_WRAPPERS = ("nohup", "time", "exec", "xargs", "env", "command", "sudo", "timeout", "nice", "stdbuf")
_WRAPPER_VALUE_FLAGS = ("-s", "-k", "--signal", "--kill-after")
_WRAPPER_NUMBER_RE = re.compile(r"\d+(\.\d+)?[smhd]?")
_REALM_SHELLS = ("bash", "sh", "zsh", "dash")
_SEGMENT_BREAKS = frozenset(("&&", "||", ";", ";;", "|", "|&", "&", "(", ")", "{", "}", "!", "$("))


def _skip_wrappers(tokens):
    while tokens:
        if _ASSIGNMENT_TOKEN_RE.match(tokens[0]):
            tokens = tokens[1:]
            continue
        if Path(tokens[0]).name not in _REALM_WRAPPERS:
            return tokens
        tokens = tokens[1:]
        while tokens and (tokens[0].startswith("-") or _WRAPPER_NUMBER_RE.fullmatch(tokens[0])):
            tokens = tokens[2:] if tokens[0] in _WRAPPER_VALUE_FLAGS else tokens[1:]
    return tokens


def _is_shell_c_cluster(token):
    return token.startswith("-") and not token.startswith("--") and "c" in token[1:]


def _hook_segments(command):
    segments = []
    current = []
    for token in _tokenize_command(command) + [";"]:
        if token in _SEGMENT_BREAKS or set(token) <= set("&|;()"):
            segments.append(current)
            current = []
            continue
        current.append(token.lstrip("`"))
    expanded = []
    for raw in segments:
        tokens = _skip_wrappers(raw)
        if len(tokens) >= 3 and Path(tokens[0]).name in _REALM_SHELLS:
            cluster = next((index for index, token in enumerate(tokens[1:], 1) if _is_shell_c_cluster(token)), None)
            if cluster is not None and cluster + 1 < len(tokens):
                expanded.extend(_hook_segments(tokens[cluster + 1]))
                continue
        expanded.append(tokens)
    return expanded


def _guild_words(tokens):
    if not tokens:
        return []
    name = Path(tokens[0]).name
    if name == "guild":
        rest = tokens[1:]
    elif _PYTHON_RE.fullmatch(name):
        starts = [
            index + 2
            for index in range(len(tokens) - 1)
            if tokens[index] == "-m" and tokens[index + 1] in _GUILD_MODULES
        ]
        if not starts:
            return []
        rest = tokens[starts[0] :]
    else:
        return []
    return [token for token in rest if not token.startswith("-")]


def deny_result(reason):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _segment_deny_reason(tokens):
    words = _guild_words(tokens)
    if words[:1] and words[0] in _DENIED_ANSWER_SUBCOMMANDS:
        return _ANSWER_DENY_REASON
    if words[:1] == ["realm"] and words[1:2] not in (["status"], ["doctor"]):
        return _REALM_DENY_REASON
    return None


def _unparseable_deny_reason(command):
    if re.search(r"\bguild\b", command) is None:
        return None
    if re.search(r"\b(answer|dismiss)\b", command):
        return _ANSWER_DENY_REASON
    if re.search(r"\brealm\b", command):
        return _REALM_DENY_REASON
    return None


def pre_answer(command):
    try:
        segments = _hook_segments(command)
    except ValueError:
        reason = _unparseable_deny_reason(command)
        return None if reason is None else deny_result(reason)
    for tokens in segments:
        reason = _segment_deny_reason(tokens)
        if reason is not None:
            return deny_result(reason)
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
