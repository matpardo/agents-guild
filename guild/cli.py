import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from guild import db, origin, paths, session_info, timeutil
from guild.commands import hook as hook_commands
from guild.context import RunContext
from guild.errors import GuildError


def _print(text):
    if text:
        sys.stdout.write(text + "\n")


def _stdout_is_colored():
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _terminal_width():
    return shutil.get_terminal_size().columns


def _print_lines(lines):
    for line in lines:
        sys.stdout.write(line + "\n")


def _handle_whoami(ctx, args):
    from guild.commands import whoami as whoami_commands

    _print(whoami_commands.run(ctx))
    return 0


def _handle_init_project(ctx, args):
    from guild.commands import init_project as init_project_commands

    _print(init_project_commands.run(ctx, args.name, args.config))
    return 0


def _handle_party_start(ctx, args):
    from guild.commands import party as party_commands

    _print(party_commands.start(ctx, args.name))
    return 0


def _handle_party_resume(ctx, args):
    from guild.commands import party as party_commands

    _print(party_commands.resume(ctx, args.party))
    return 0


def _handle_party_close(ctx, args):
    from guild.commands import party as party_commands

    _print(party_commands.close(ctx))
    return 0


def _handle_quest_add(ctx, args):
    from guild.commands import quest as quest_commands

    _print(quest_commands.add(ctx, args.slug, args.title, args.epic, args.tasks, args.no_epic))
    return 0


def _handle_task_add(ctx, args):
    from guild.commands import task as task_commands

    quest, tid = args.ref.split("/", 1)
    _print(task_commands.add(ctx, quest, tid, args.title))
    return 0


def _handle_task_start(ctx, args):
    from guild.commands import task as task_commands

    quest, tid = args.ref.split("/", 1)
    _print(task_commands.start(ctx, quest, tid, args.summary))
    return 0


def _handle_task_block(ctx, args):
    from guild.commands import task as task_commands

    quest, tid = args.ref.split("/", 1)
    _print(task_commands.block(ctx, quest, tid, args.reason))
    return 0


def _handle_task_done(ctx, args):
    from guild.commands import task as task_commands

    quest, tid = args.ref.split("/", 1)
    _print(task_commands.done(ctx, quest, tid, args.summary))
    return 0


def _handle_pr_track(ctx, args):
    from guild.commands import pr as pr_commands

    _print(pr_commands.track(ctx, args.ref, args.task, args.what, args.waits))
    return 0


def _handle_pr_set(ctx, args):
    from guild.commands import pr as pr_commands

    _print(pr_commands.set_(ctx, args.ref, args.lifecycle, args.waits))
    return 0


def _handle_ask(ctx, args):
    from guild.commands import ask as ask_commands

    _print(ask_commands.create(ctx, args.question, args.context, args.ref or [], args.option or []))
    return 0


def _handle_answer(ctx, args):
    from guild.commands import ask as ask_commands

    _print(ask_commands.answer(ctx, args.id, args.text))
    return 0


def _handle_dismiss(ctx, args):
    from guild.commands import ask as ask_commands

    _print(ask_commands.dismiss(ctx, args.id))
    return 0


def _handle_asks(ctx, args):
    from guild.commands import board as board_commands

    _print_lines(board_commands.render_asks(ctx, None, _stdout_is_colored(), _terminal_width(), True))
    return 0


def _handle_notice_create(ctx, args):
    from guild.commands import notice as notice_commands

    _print(notice_commands.create(ctx, args.text, args.to, args.ttl, args.until))
    return 0


def _handle_notice_close(ctx, args):
    from guild.commands import notice as notice_commands

    _print(notice_commands.close(ctx, args.id))
    return 0


def _handle_notices(ctx, args):
    from guild.commands import notice as notice_commands

    _print_lines(notice_commands.list_active(ctx))
    return 0


def _handle_claim(ctx, args):
    from guild.commands import claim as claim_commands

    _print(claim_commands.claim(ctx, args.area, args.ttl))
    return 0


def _handle_release(ctx, args):
    from guild.commands import claim as claim_commands

    _print(claim_commands.release(ctx, args.area))
    return 0


def _handle_claims(ctx, args):
    from guild.commands import claim as claim_commands

    rows = claim_commands.list_claims(ctx.conn, ctx.now)
    _print_lines(
        ["{} — {} until {}".format(row["area"], row["party"], row["expires_at"]) for row in rows]
    )
    return 0


def _handle_board(ctx, args):
    from guild.commands import board as board_commands

    _print_lines(board_commands.render_board(ctx, args.party, _stdout_is_colored(), _terminal_width()))
    return 0


def _handle_next(ctx, args):
    from guild.commands import next as next_commands

    _print_lines(next_commands.run(ctx, args.all))
    return 0


def _handle_sync(ctx, args):
    from guild.commands import sync as sync_commands

    failures = sync_commands.run(ctx, args.source)
    for failure in failures:
        sys.stderr.write("guild: sync failed for {}\n".format(failure))
    return 1 if failures else 0


def _handle_brief(ctx, args):
    from guild.commands import brief as brief_commands

    _print_lines(brief_commands.render_brief(ctx))
    return 0


def _handle_inbox(ctx, args):
    from guild import identity
    from guild.commands import inbox as inbox_commands

    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    lines, seq = inbox_commands.new_lines(ctx, binding)
    _print_lines(lines)
    with db.writing(ctx.conn):
        inbox_commands.advance_cursor(ctx.conn, identity.cursor_key(ctx.session_id), seq)
    return 0


def _handle_statusline(ctx, args):
    from guild.commands import statusline as statusline_commands

    if args.ctx is not None:
        statusline_commands.record_ctx(ctx.state_dir, args.session, args.ctx)
    _print(statusline_commands.render(ctx, args.session))
    return 0


def _handle_seed(ctx, args):
    from guild.commands import seed as seed_commands

    _print(seed_commands.run(ctx, args.file))
    return 0


def _handle_rebuild(ctx, args):
    from guild.commands import rebuild as rebuild_commands

    _print(rebuild_commands.run(ctx))
    return 0


def _handle_export(ctx, args):
    from guild.commands import export as export_commands

    _print_lines(export_commands.run(ctx, args.visibility))
    return 0


def _add_party_parser(subparsers):
    parser = subparsers.add_parser("party")
    actions = parser.add_subparsers(dest="party_action", required=True)

    start = actions.add_parser("start")
    start.add_argument("name")
    start.set_defaults(handler=_handle_party_start)

    resume = actions.add_parser("resume")
    resume.add_argument("party")
    resume.set_defaults(handler=_handle_party_resume)

    close = actions.add_parser("close")
    close.set_defaults(handler=_handle_party_close)


def _add_quest_parser(subparsers):
    parser = subparsers.add_parser("quest")
    actions = parser.add_subparsers(dest="quest_action", required=True)

    add = actions.add_parser("add")
    add.add_argument("slug")
    add.add_argument("--title", required=True)
    add.add_argument("--epic")
    add.add_argument("--tasks")
    add.add_argument("--no-epic", action="store_true")
    add.set_defaults(handler=_handle_quest_add)


def _add_task_parser(subparsers):
    parser = subparsers.add_parser("task")
    actions = parser.add_subparsers(dest="task_action", required=True)

    add = actions.add_parser("add")
    add.add_argument("ref")
    add.add_argument("--title", required=True)
    add.set_defaults(handler=_handle_task_add)

    start = actions.add_parser("start")
    start.add_argument("ref")
    start.add_argument("--summary")
    start.set_defaults(handler=_handle_task_start)

    block = actions.add_parser("block")
    block.add_argument("ref")
    block.add_argument("--reason", required=True)
    block.set_defaults(handler=_handle_task_block)

    done = actions.add_parser("done")
    done.add_argument("ref")
    done.add_argument("--summary")
    done.set_defaults(handler=_handle_task_done)


def _add_pr_parser(subparsers):
    parser = subparsers.add_parser("pr")
    actions = parser.add_subparsers(dest="pr_action", required=True)

    track = actions.add_parser("track")
    track.add_argument("ref")
    track.add_argument("--task", required=True)
    track.add_argument("--what", required=True)
    track.add_argument("--waits", required=True)
    track.set_defaults(handler=_handle_pr_track)

    set_parser = actions.add_parser("set")
    set_parser.add_argument("ref")
    set_parser.add_argument("--lifecycle", choices=["draft", "converging", "needs-human", "ready"])
    set_parser.add_argument("--waits")
    set_parser.set_defaults(handler=_handle_pr_set)


def _add_notice_parser(subparsers):
    parser = subparsers.add_parser("notice")
    actions = parser.add_subparsers(dest="notice_action", required=True)

    create = actions.add_parser("create")
    create.add_argument("text")
    create.add_argument("--to", required=True)
    create.add_argument("--ttl", required=True)
    create.add_argument("--until")
    create.set_defaults(handler=_handle_notice_create)

    close = actions.add_parser("close")
    close.add_argument("id", type=int)
    close.set_defaults(handler=_handle_notice_close)


def build_parser():
    parser = argparse.ArgumentParser(prog="guild")
    subparsers = parser.add_subparsers(dest="command", required=True)

    whoami = subparsers.add_parser("whoami")
    whoami.set_defaults(handler=_handle_whoami)

    init_project = subparsers.add_parser("init-project")
    init_project.add_argument("name")
    init_project.add_argument("--config", required=True)
    init_project.set_defaults(handler=_handle_init_project)

    _add_party_parser(subparsers)
    _add_quest_parser(subparsers)
    _add_task_parser(subparsers)
    _add_pr_parser(subparsers)

    ask = subparsers.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--context", required=True)
    ask.add_argument("--ref", action="append")
    ask.add_argument("--option", action="append")
    ask.set_defaults(handler=_handle_ask)

    answer = subparsers.add_parser("answer")
    answer.add_argument("id", type=int)
    answer.add_argument("text")
    answer.set_defaults(handler=_handle_answer)

    dismiss = subparsers.add_parser("dismiss")
    dismiss.add_argument("id", type=int)
    dismiss.set_defaults(handler=_handle_dismiss)

    asks = subparsers.add_parser("asks")
    asks.set_defaults(handler=_handle_asks)

    _add_notice_parser(subparsers)

    notices = subparsers.add_parser("notices")
    notices.set_defaults(handler=_handle_notices)

    claim = subparsers.add_parser("claim")
    claim.add_argument("area")
    claim.add_argument("--ttl", required=True)
    claim.set_defaults(handler=_handle_claim)

    release = subparsers.add_parser("release")
    release.add_argument("area")
    release.set_defaults(handler=_handle_release)

    claims = subparsers.add_parser("claims")
    claims.set_defaults(handler=_handle_claims)

    board = subparsers.add_parser("board")
    board.add_argument("--party")
    board.set_defaults(handler=_handle_board)

    next_parser = subparsers.add_parser("next")
    next_parser.add_argument("--all", action="store_true")
    next_parser.set_defaults(handler=_handle_next)

    sync = subparsers.add_parser("sync")
    sync.add_argument("--source", required=True, choices=["gh", "jira", "sdd"])
    sync.set_defaults(handler=_handle_sync)

    brief = subparsers.add_parser("brief")
    brief.set_defaults(handler=_handle_brief)

    inbox = subparsers.add_parser("inbox")
    inbox.add_argument("--since-last", action="store_true")
    inbox.set_defaults(handler=_handle_inbox)

    statusline = subparsers.add_parser("statusline")
    statusline.add_argument("--session", required=True)
    statusline.add_argument("--ctx", type=int)
    statusline.set_defaults(handler=_handle_statusline)

    hook = subparsers.add_parser("hook")
    hook.add_argument(
        "hook_name", choices=["session-start", "prompt-submit", "pre-push", "post-tool-use"]
    )

    seed = subparsers.add_parser("seed")
    seed.add_argument("file")
    seed.set_defaults(handler=_handle_seed)

    rebuild = subparsers.add_parser("rebuild")
    rebuild.set_defaults(handler=_handle_rebuild)

    export = subparsers.add_parser("export")
    export.add_argument("--visibility", required=True, choices=["guild"])
    export.set_defaults(handler=_handle_export)

    return parser


def _build_context(session_id, cwd):
    conn = db.connect(paths.db_path())
    return RunContext(
        conn,
        session_id,
        cwd,
        timeutil.utcnow(),
        origin.current_origin(),
        paths.claude_sessions_dir(),
        paths.projects_config_dir(),
        paths.state_dir(),
    )


def _run_pre_push_hook(stdin_data):
    try:
        tool_input = stdin_data.get("tool_input", {})
        command = tool_input.get("command", "")
        cwd = stdin_data.get("cwd", ".")
        result = hook_commands.pre_push(command, cwd)
    except Exception as error:
        sys.stdout.write(json.dumps({"systemMessage": "guild hook error: {}".format(error)}) + "\n")
        return 0
    if result["system_message"] is not None:
        sys.stdout.write(json.dumps({"systemMessage": result["system_message"]}) + "\n")
        return 0
    if result["blocked"]:
        sys.stderr.write(result["message"] + "\n")
        return 2
    return 0


def _run_stateful_hook(hook_name, stdin_data):
    try:
        session_id = stdin_data.get("session_id")
        cwd = Path(stdin_data.get("cwd", str(Path.cwd())))
        ctx = _build_context(session_id, cwd)
        if hook_name == "session-start":
            text = hook_commands.session_start(ctx)
        elif hook_name == "post-tool-use":
            text = hook_commands.post_tool_use(ctx)
        else:
            text = hook_commands.prompt_submit(ctx)
    except Exception as error:
        sys.stdout.write("guild hook error: {}\n".format(error))
        return 0
    _print(text)
    return 0


def _dispatch_hook(args):
    raw = sys.stdin.read()
    try:
        stdin_data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        stdin_data = {}
    if args.hook_name == "pre-push":
        return _run_pre_push_hook(stdin_data)
    return _run_stateful_hook(args.hook_name, stdin_data)


def main(argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "hook":
        return _dispatch_hook(args)
    try:
        ctx = _build_context(session_info.current_session_id(), Path.cwd())
        return args.handler(ctx, args)
    except GuildError as error:
        sys.stderr.write("guild: {}\n".format(error.message))
        return error.exit_code
