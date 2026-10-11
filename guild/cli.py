import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from guild import db, notify, origin, paths, session_info, timeutil
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


def _handle_doctor(ctx, args):
    from guild.commands import doctor as doctor_commands

    message, exit_code = doctor_commands.run(ctx, args.scan_prs)
    _print(message)
    return exit_code


def _handle_wire_settings(ctx, args):
    from guild.commands import wire_settings as wire_settings_commands

    _print(wire_settings_commands.run())
    return 0


def _handle_revive(ctx, args):
    from guild import tmux_windows
    from guild.commands import revive as revive_commands

    ask_numbers = input if sys.stdin.isatty() else None
    _print(
        revive_commands.run(
            ctx,
            args.party,
            args.all,
            args.list,
            paths.claude_projects_dir(),
            tmux_windows.Tmux(),
            ask_numbers,
        )
    )
    return 0


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

    _print(party_commands.start(ctx, args.name, args.keeper))
    return 0


def _handle_party_resume(ctx, args):
    from guild.commands import party as party_commands

    _print(party_commands.resume(ctx, args.party, args.session, None))
    return 0


def _handle_party_close(ctx, args):
    from guild.commands import party as party_commands

    _print(party_commands.close(ctx, args.name, args.force))
    return 0


def _handle_quest_done(ctx, args):
    from guild.commands import quest as quest_commands

    _print(quest_commands.done(ctx, args.slug, args.accept_drift, args.force))
    return 0


def _handle_quest_incomplete(ctx, args):
    from guild.commands import quest as quest_commands

    _print(quest_commands.incomplete(ctx, args.slug, args.reason))
    return 0


def _handle_quest_add(ctx, args):
    from guild.commands import quest as quest_commands

    _print(quest_commands.add(
        ctx, args.slug, args.title, args.epic, args.tasks, args.titles, args.no_epic, args.followups_of
    ))
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

    _print(
        pr_commands.track(
            ctx,
            args.ref,
            args.task,
            args.card,
            args.what,
            args.waits,
            args.needs_human_pr_review,
            args.fixes_main,
            args.fixes_flaky,
        )
    )
    return 0


def _handle_pr_set(ctx, args):
    from guild.commands import pr as pr_commands

    _print(
        pr_commands.set_(
            ctx,
            args.ref,
            args.lifecycle,
            args.waits,
            args.needs_ask_answer,
            args.needs_human_pr_review,
            args.fixes_main,
            args.fixes_flaky,
        )
    )
    return 0


def _handle_pr_ready_check(ctx, args):
    from guild.commands import pr as pr_commands

    lines, exit_code = pr_commands.ready_check(ctx, args.ref)
    _print_lines(lines)
    return exit_code


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


def _handle_ask_detail(ctx, args):
    from guild import ask_detail

    if args.all or args.answered or args.page is not None or args.party is not None or args.since is not None:
        raise GuildError("guild asks <id> takes no filters", 1)
    row = ctx.conn.execute("SELECT * FROM asks WHERE id = ?", (args.ask_id,)).fetchone()
    if row is None:
        raise GuildError("unknown ask #{}".format(args.ask_id), 1)
    _print_lines(ask_detail.render_lines(ask_detail.build(ctx, row)))
    return 0


def _handle_asks(ctx, args):
    from guild.commands import board as board_commands

    if args.ask_id is not None:
        return _handle_ask_detail(ctx, args)
    if args.all and args.answered:
        raise GuildError("--all and --answered are exclusive", 1)
    if args.page is not None and not args.answered:
        raise GuildError("--page needs --answered", 1)
    if not args.all and not args.answered:
        if args.party is not None or args.since is not None:
            raise GuildError("--party/--since need --all or --answered", 1)
        _print_lines(board_commands.render_asks(ctx, None, _stdout_is_colored(), _terminal_width(), True))
        return 0
    since_cutoff = None
    if args.since is not None:
        since_cutoff = ctx.now - timeutil.parse_duration(args.since)
    if args.answered:
        page = 1 if args.page is None else args.page
        _print_lines(
            board_commands.render_answered_asks(
                ctx, args.party, since_cutoff, page, _stdout_is_colored(), _terminal_width()
            )
        )
        return 0
    _print_lines(
        board_commands.render_all_asks(
            ctx, args.party, since_cutoff, _stdout_is_colored(), _terminal_width()
        )
    )
    return 0


def _handle_notice_create(ctx, args):
    from guild.commands import notice as notice_commands

    _print(notice_commands.create(ctx, args.text, args.to, args.ttl, args.until))
    return 0


def _handle_notice_close(ctx, args):
    from guild.commands import notice as notice_commands

    _print(notice_commands.close(ctx, args.id))
    return 0


def _handle_notice_seen(ctx, args):
    from guild.commands import notice as notice_commands

    if args.all:
        _print(notice_commands.mark_all_seen(ctx))
        return 0
    _print(notice_commands.mark_seen(ctx, args.id))
    return 0


def _handle_notice_unseen(ctx, args):
    from guild.commands import notice as notice_commands

    _print(notice_commands.mark_unseen(ctx, args.id))
    return 0


def _handle_notices(ctx, args):
    from guild.commands import notice as notice_commands

    _print_lines(notice_commands.list_active(ctx))
    return 0


def _handle_claim(ctx, args):
    from guild.commands import claim as claim_commands

    if args.area == "check":
        if args.ttl is not None:
            raise GuildError("`guild claim check` does not take --ttl", 1)
        if args.check_area is None:
            raise GuildError("`guild claim check` requires an area", 1)
        message, exit_code = claim_commands.check(ctx, args.check_area)
        _print(message)
        return exit_code
    if args.check_area is not None:
        raise GuildError("unexpected extra argument '{}'".format(args.check_area), 1)
    if args.ttl is None:
        raise GuildError("--ttl is required", 1)
    _print(claim_commands.claim(ctx, args.area, args.ttl, None))
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


def _handle_raid_join(ctx, args):
    from guild.commands import raid as raid_commands

    _print(raid_commands.join(ctx, args.name, args.ttl, args.until_leave, args.lead))
    return 0


def _handle_raid_leave(ctx, args):
    from guild.commands import raid as raid_commands

    _print(raid_commands.leave(ctx, args.name))
    return 0


def _handle_raid_pause(ctx, args):
    from guild.commands import raid_pause as raid_pause_commands

    _print(raid_pause_commands.pause(ctx, args.name))
    return 0


def _handle_raid_resume(ctx, args):
    from guild.commands import raid_pause as raid_pause_commands

    _print(raid_pause_commands.resume(ctx, args.name))
    return 0


def _handle_raids(ctx, args):
    from guild.commands import raid as raid_commands

    _print_lines(raid_commands.list_raids(ctx))
    return 0


def _handle_merge_queue(ctx, args):
    from guild.commands import merge_queue as merge_queue_commands

    _print_lines(merge_queue_commands.run(ctx, args.raid, args.party))
    return 0


def _handle_merge_queue_pin(ctx, args):
    from guild.commands import merge_queue as merge_queue_commands

    _print(merge_queue_commands.pin(ctx, args.ref, args.before))
    return 0


def _handle_merge_queue_unpin(ctx, args):
    from guild.commands import merge_queue as merge_queue_commands

    _print(merge_queue_commands.unpin(ctx, args.ref, args.before))
    return 0


def _handle_main_red(ctx, args):
    from guild.commands import main_status as main_status_commands

    _print(main_status_commands.red(ctx, args.repo, args.reason))
    return 0


def _handle_main_green(ctx, args):
    from guild.commands import main_status as main_status_commands

    _print(main_status_commands.green(ctx, args.repo))
    return 0


def _handle_history(ctx, args):
    from guild.commands import history as history_commands

    _print_lines(history_commands.run(ctx, args.party, args.raid, args.project))
    return 0


def _handle_cost(ctx, args):
    from guild.commands import cost as cost_commands

    _print_lines(cost_commands.run(ctx, args.since, args.by, args.project))
    return 0


def _handle_board(ctx, args):
    from guild.commands import board as board_commands

    _print_lines(
        board_commands.render_board(
            ctx, args.party, args.raid, _stdout_is_colored(), _terminal_width()
        )
    )
    return 0


def _handle_handoff(ctx, args):
    import time

    from guild import tmux_windows
    from guild.commands import handoff as handoff_commands

    if args.action == "prune":
        provided = (
            ("--in-flight", args.in_flight is not None),
            ("--learned", args.learned is not None),
            ("--model", args.model is not None),
            ("--respawn", args.respawn),
        )
        for flag, given in provided:
            if given:
                raise GuildError("handoff prune does not take {}".format(flag), 1)
        _print(handoff_commands.run_prune(ctx, args.dry_run))
        return 0
    if args.dry_run:
        raise GuildError("--dry-run only applies to handoff prune", 1)
    if args.in_flight is None:
        raise GuildError("--in-flight is required", 1)
    if args.learned is None:
        raise GuildError("--learned is required", 1)
    tmux = tmux_windows.Tmux()
    text, pane_to_close = handoff_commands.run(
        ctx, args.in_flight, args.learned, args.model, args.respawn, tmux, os.environ.get("TMUX_PANE"), time.sleep
    )
    _print(text)
    sys.stdout.flush()
    if pane_to_close is not None:
        tmux_windows.kill_pane(tmux, pane_to_close)
    return 0


def _handle_next(ctx, args):
    from guild import identity
    from guild.commands import next as next_commands

    binding = identity.require_binding(ctx.conn, ctx.session_id)
    _print_lines(next_commands.run(ctx, binding, args.all, not args.all))
    return 0


def _handle_sync(ctx, args):
    from guild import lifecycle
    from guild.commands import sync as sync_commands

    failures = sync_commands.run(ctx, args.source, args.all_projects, lifecycle.run_process)
    for failure in failures:
        sys.stderr.write("guild: sync failed for {}\n".format(failure))
    return 1 if failures else 0


def _handle_lifecycle_run(ctx, args):
    from guild import lifecycle
    from guild.commands import lifecycle as lifecycle_commands

    _print(lifecycle_commands.run_manual(ctx, args.event, args.repo, args.dry_run, lifecycle.run_process))
    return 0


def _handle_resources(ctx, args):
    from guild.commands import resources as resources_commands

    if args.resources_action == "collect":
        _print(resources_commands.run_collect(ctx))
        return 0
    _print_lines(resources_commands.run_report(ctx, args.project, args.since))
    return 0


def _handle_timer(ctx, args):
    from guild.commands import timer as timer_commands

    unit = timer_commands.UNITS[args.timer_unit]
    guild_executable = shutil.which("guild")
    if args.timer_action == "print":
        _print(timer_commands.print_units(unit, guild_executable, args.every))
        return 0
    systemctl_available = shutil.which("systemctl") is not None
    if args.timer_action == "uninstall":
        _print(
            timer_commands.uninstall(
                unit, paths.systemd_user_dir(), timer_commands.run_systemctl, sys.platform, systemctl_available
            )
        )
        return 0
    _print(
        timer_commands.install(
            unit,
            paths.systemd_user_dir(),
            guild_executable,
            args.every,
            timer_commands.run_systemctl,
            sys.platform,
            systemctl_available,
        )
    )
    return 0


def _handle_dispatch(ctx, args):
    from guild import tmux_windows
    from guild.commands import dispatch as dispatch_commands

    if args.dispatch_action == "status":
        _print_lines(dispatch_commands.status(ctx))
        return 0
    _print_lines(dispatch_commands.run(ctx, args.dry_run, tmux_windows.Tmux(), notify.spawn_detached))
    return 0


def _handle_drift(ctx, args):
    from guild import config
    from guild.commands import drift as drift_commands

    project = config.require_project(ctx.cwd, ctx.projects_dir)
    _print_lines(drift_commands.run(ctx, project, args.epic, args.all))
    return 0


def _handle_brief(ctx, args):
    from guild.commands import brief as brief_commands
    from guild.commands import task_brief

    if args.task is None:
        _print_lines(brief_commands.render_brief(ctx))
        return 0
    _print_lines(task_brief.render_from_ref(ctx, args.task))
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


def _handle_web(ctx, args):
    from guild.commands import web as web_commands

    return web_commands.run(args.port)


def _add_party_parser(subparsers):
    parser = subparsers.add_parser("party")
    actions = parser.add_subparsers(dest="party_action", required=True)

    start = actions.add_parser("start")
    start.add_argument("name")
    start.add_argument("--keeper", action="store_true")
    start.set_defaults(handler=_handle_party_start)

    resume = actions.add_parser("resume")
    resume.add_argument("party")
    resume.add_argument("--session")
    resume.set_defaults(handler=_handle_party_resume)

    close = actions.add_parser("close")
    close.add_argument("name", nargs="?")
    close.add_argument("--force", action="store_true")
    close.set_defaults(handler=_handle_party_close)


def _add_quest_parser(subparsers):
    parser = subparsers.add_parser("quest")
    actions = parser.add_subparsers(dest="quest_action", required=True)

    add = actions.add_parser("add")
    add.add_argument("slug")
    add.add_argument("--title", required=True)
    add.add_argument("--epic")
    add.add_argument("--tasks")
    add.add_argument("--titles")
    add.add_argument("--no-epic", action="store_true")
    add.add_argument("--followups-of")
    add.set_defaults(handler=_handle_quest_add)

    done = actions.add_parser("done")
    done.add_argument("slug")
    done.add_argument("--accept-drift", action="store_true")
    done.add_argument("--force", action="store_true")
    done.set_defaults(handler=_handle_quest_done)

    incomplete = actions.add_parser("incomplete")
    incomplete.add_argument("slug")
    incomplete.add_argument("--reason", required=True)
    incomplete.set_defaults(handler=_handle_quest_incomplete)


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


def _add_flag_pair(parser, name, dest):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--" + name, dest=dest, action="store_const", const=True)
    group.add_argument("--no-" + name, dest=dest, action="store_const", const=False)


def _add_pr_parser(subparsers):
    parser = subparsers.add_parser("pr")
    actions = parser.add_subparsers(dest="pr_action", required=True)

    track = actions.add_parser("track")
    track.add_argument("ref")
    target = track.add_mutually_exclusive_group(required=True)
    target.add_argument("--task")
    target.add_argument("--card")
    track.add_argument("--what", required=True)
    track.add_argument("--waits", required=True)
    track.add_argument("--needs-human-pr-review", action="store_true")
    track.add_argument("--fixes-main", action="store_true")
    track.add_argument("--fixes-flaky", action="store_true")
    track.set_defaults(handler=_handle_pr_track)

    set_parser = actions.add_parser("set")
    set_parser.add_argument("ref")
    set_parser.add_argument("--lifecycle", choices=["draft", "converging", "ready"])
    set_parser.add_argument("--waits")
    _add_flag_pair(set_parser, "needs-ask-answer", "needs_ask_answer")
    _add_flag_pair(set_parser, "needs-human-pr-review", "needs_human_pr_review")
    _add_flag_pair(set_parser, "fixes-main", "fixes_main")
    _add_flag_pair(set_parser, "fixes-flaky", "fixes_flaky")
    set_parser.set_defaults(handler=_handle_pr_set)

    ready_check = actions.add_parser("ready-check")
    ready_check.add_argument("ref")
    ready_check.set_defaults(handler=_handle_pr_ready_check)


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

    seen = actions.add_parser("seen")
    seen_target = seen.add_mutually_exclusive_group(required=True)
    seen_target.add_argument("id", type=int, nargs="?")
    seen_target.add_argument("--all", action="store_true")
    seen.set_defaults(handler=_handle_notice_seen)

    unseen = actions.add_parser("unseen")
    unseen.add_argument("id", type=int)
    unseen.set_defaults(handler=_handle_notice_unseen)


def _add_raid_parser(subparsers):
    parser = subparsers.add_parser("raid")
    actions = parser.add_subparsers(dest="raid_action", required=True)

    join = actions.add_parser("join")
    join.add_argument("name")
    join_mode = join.add_mutually_exclusive_group(required=True)
    join_mode.add_argument("--ttl")
    join_mode.add_argument("--until-leave", action="store_true")
    join.add_argument("--lead", action="store_true")
    join.set_defaults(handler=_handle_raid_join)

    leave = actions.add_parser("leave")
    leave.add_argument("name")
    leave.set_defaults(handler=_handle_raid_leave)

    pause = actions.add_parser("pause")
    pause.add_argument("name")
    pause.set_defaults(handler=_handle_raid_pause)

    resume = actions.add_parser("resume")
    resume.add_argument("name")
    resume.set_defaults(handler=_handle_raid_resume)


def _add_merge_queue_parser(subparsers):
    parser = subparsers.add_parser("merge-queue")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--raid")
    scope.add_argument("--party")
    parser.set_defaults(handler=_handle_merge_queue)
    actions = parser.add_subparsers(dest="merge_queue_action", required=False)

    pin = actions.add_parser("pin")
    pin.add_argument("ref")
    pin.add_argument("--before", required=True)
    pin.set_defaults(handler=_handle_merge_queue_pin)

    unpin = actions.add_parser("unpin")
    unpin.add_argument("ref")
    unpin.add_argument("--before", required=True)
    unpin.set_defaults(handler=_handle_merge_queue_unpin)


def _add_main_parser(subparsers):
    parser = subparsers.add_parser("main")
    actions = parser.add_subparsers(dest="main_action", required=True)

    red = actions.add_parser("red")
    red.add_argument("repo")
    red.add_argument("--reason", required=True)
    red.set_defaults(handler=_handle_main_red)

    green = actions.add_parser("green")
    green.add_argument("repo")
    green.set_defaults(handler=_handle_main_green)


def _add_timer_parser(subparsers, command_name, timer_unit):
    parser = subparsers.add_parser(command_name)
    actions = parser.add_subparsers(dest="timer_action", required=True)
    for action in ("install", "print"):
        action_parser = actions.add_parser(action)
        action_parser.add_argument("--every", required=True)
        action_parser.set_defaults(handler=_handle_timer, timer_unit=timer_unit)
    uninstall = actions.add_parser("uninstall")
    uninstall.set_defaults(handler=_handle_timer, timer_unit=timer_unit)


def build_parser():
    parser = argparse.ArgumentParser(prog="guild")
    subparsers = parser.add_subparsers(dest="command", required=True)

    whoami = subparsers.add_parser("whoami")
    whoami.set_defaults(handler=_handle_whoami)

    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--scan-prs", action="store_true")
    doctor.set_defaults(handler=_handle_doctor)

    wire_settings = subparsers.add_parser("wire-settings")
    wire_settings.set_defaults(handler=_handle_wire_settings)

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
    asks.add_argument("ask_id", type=int, nargs="?")
    asks.add_argument("--all", action="store_true")
    asks.add_argument("--answered", action="store_true")
    asks.add_argument("--page", type=int)
    asks.add_argument("--party")
    asks.add_argument("--since")
    asks.set_defaults(handler=_handle_asks)

    _add_notice_parser(subparsers)

    notices = subparsers.add_parser("notices")
    notices.set_defaults(handler=_handle_notices)

    claim = subparsers.add_parser("claim")
    claim.add_argument("area")
    claim.add_argument("check_area", nargs="?")
    claim.add_argument("--ttl")
    claim.set_defaults(handler=_handle_claim)

    release = subparsers.add_parser("release")
    release.add_argument("area")
    release.set_defaults(handler=_handle_release)

    claims = subparsers.add_parser("claims")
    claims.set_defaults(handler=_handle_claims)

    _add_raid_parser(subparsers)

    raids = subparsers.add_parser("raids")
    raids.set_defaults(handler=_handle_raids)

    _add_merge_queue_parser(subparsers)
    _add_main_parser(subparsers)

    board = subparsers.add_parser("board")
    board_filter = board.add_mutually_exclusive_group()
    board_filter.add_argument("--party")
    board_filter.add_argument("--raid")
    board.set_defaults(handler=_handle_board)

    history = subparsers.add_parser("history")
    history.add_argument("--party")
    history.add_argument("--raid")
    history.add_argument("--project")
    history.set_defaults(handler=_handle_history)

    cost = subparsers.add_parser("cost")
    cost.add_argument("--since", default=None)
    cost.add_argument("--by", choices=("session", "party", "model", "quest", "task"), default="session")
    cost.add_argument("--project", default=None)
    cost.set_defaults(handler=_handle_cost)

    next_parser = subparsers.add_parser("next")
    next_parser.add_argument("--all", action="store_true")
    next_parser.set_defaults(handler=_handle_next)

    handoff = subparsers.add_parser("handoff")
    handoff.add_argument("action", nargs="?", choices=["prune"])
    handoff.add_argument("--in-flight")
    handoff.add_argument("--learned")
    handoff.add_argument("--model")
    handoff.add_argument("--dry-run", action="store_true")
    handoff.add_argument("--respawn", action="store_true")
    handoff.set_defaults(handler=_handle_handoff)

    sync = subparsers.add_parser("sync")
    sync.add_argument("--source", required=True, choices=["gh", "sdd", "tracker"])
    sync.add_argument("--all-projects", action="store_true")
    sync.set_defaults(handler=_handle_sync)

    lifecycle_parser = subparsers.add_parser("lifecycle")
    lifecycle_actions = lifecycle_parser.add_subparsers(dest="lifecycle_action", required=True)
    lifecycle_run = lifecycle_actions.add_parser("run")
    lifecycle_run.add_argument("event", choices=["on_pr_merged", "on_pr_closed"])
    lifecycle_run.add_argument("--repo")
    lifecycle_run.add_argument("--dry-run", action="store_true")
    lifecycle_run.set_defaults(handler=_handle_lifecycle_run)

    resources = subparsers.add_parser("resources")
    resources.add_argument("--project")
    resources.add_argument("--since", default="1d")
    resources.set_defaults(handler=_handle_resources)
    resources_actions = resources.add_subparsers(dest="resources_action", required=False)
    resources_actions.add_parser("collect")

    dispatch = subparsers.add_parser("dispatch")
    dispatch_actions = dispatch.add_subparsers(dest="dispatch_action", required=True)
    dispatch_run = dispatch_actions.add_parser("run")
    dispatch_run.add_argument("--dry-run", action="store_true")
    dispatch_run.set_defaults(handler=_handle_dispatch)
    dispatch_status = dispatch_actions.add_parser("status")
    dispatch_status.set_defaults(handler=_handle_dispatch)

    _add_timer_parser(subparsers, "sync-timer", "sync-gh")
    _add_timer_parser(subparsers, "sync-sdd-timer", "sync-sdd")
    _add_timer_parser(subparsers, "sync-tracker-timer", "sync-tracker")
    _add_timer_parser(subparsers, "resources-timer", "resources-collect")
    _add_timer_parser(subparsers, "dispatch-timer", "dispatch")

    drift = subparsers.add_parser("drift")
    drift_scope = drift.add_mutually_exclusive_group()
    drift_scope.add_argument("--epic")
    drift_scope.add_argument("--all", action="store_true")
    drift.set_defaults(handler=_handle_drift)

    revive = subparsers.add_parser("revive")
    revive.add_argument("--party", action="append", default=[])
    revive.add_argument("--all", action="store_true")
    revive.add_argument("--list", action="store_true")
    revive.set_defaults(handler=_handle_revive)

    brief = subparsers.add_parser("brief")
    brief.add_argument("task", nargs="?")
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
        "hook_name",
        choices=[
            "session-start",
            "prompt-submit",
            "pre-push",
            "pre-pr-owner",
            "post-tool-use",
            "pre-edit",
            "pre-commit",
            "notification",
            "stop",
        ],
    )

    seed = subparsers.add_parser("seed")
    seed.add_argument("file")
    seed.set_defaults(handler=_handle_seed)

    rebuild = subparsers.add_parser("rebuild")
    rebuild.set_defaults(handler=_handle_rebuild)

    export = subparsers.add_parser("export")
    export.add_argument("--visibility", required=True, choices=["guild"])
    export.set_defaults(handler=_handle_export)

    web = subparsers.add_parser("web")
    web.add_argument("--port", type=int, default=8765)
    web.set_defaults(handler=_handle_web)

    return parser


def _build_context(session_id, cwd):
    conn = db.connect(paths.db_path())
    paths.ensure_private_dir(paths.state_dir())
    paths.ensure_private_dir(paths.handoffs_dir())
    paths.ensure_private_dir(paths.projects_config_dir())
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
        cwd = Path(stdin_data.get("cwd", "."))
        ctx = _build_context(stdin_data.get("session_id"), cwd)
        result = hook_commands.pre_push(ctx, command)
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


def _run_pre_pr_owner_hook(stdin_data):
    try:
        command = stdin_data.get("tool_input", {}).get("command", "")
        cwd = Path(stdin_data.get("cwd", str(Path.cwd())))
        ctx = _build_context(stdin_data.get("session_id"), cwd)
        result = hook_commands.pre_pr_owner(ctx, command)
    except Exception as error:
        sys.stdout.write(json.dumps({"systemMessage": "guild hook error: {}".format(error)}) + "\n")
        return 0
    if result is not None:
        sys.stdout.write(json.dumps(result) + "\n")
    return 0


def _run_pre_edit_hook(stdin_data):
    try:
        session_id = stdin_data.get("session_id")
        cwd = Path(stdin_data.get("cwd", str(Path.cwd())))
        ctx = _build_context(session_id, cwd)
        tool_name = stdin_data.get("tool_name")
        tool_input = stdin_data.get("tool_input", {})
        agent_type = stdin_data.get("agent_type")
        result = hook_commands.pre_edit(ctx, tool_name, tool_input, agent_type)
    except Exception as error:
        sys.stdout.write(json.dumps({"systemMessage": "guild hook error: {}".format(error)}) + "\n")
        return 0
    if result is not None:
        sys.stdout.write(json.dumps(result) + "\n")
    return 0


def _run_stateful_hook(hook_name, stdin_data):
    try:
        session_id = stdin_data.get("session_id")
        cwd = Path(stdin_data.get("cwd", str(Path.cwd())))
        ctx = _build_context(session_id, cwd)
        if hook_name == "session-start":
            text = hook_commands.session_start(
                ctx, os.environ.get("GUILD_RESUME") or None, stdin_data.get("permission_mode")
            )
        elif hook_name == "post-tool-use":
            text = hook_commands.post_tool_use(ctx)
        elif hook_name == "notification":
            hook_commands.notification(
                ctx, stdin_data.get("notification_type"), stdin_data.get("message"), notify.spawn_detached
            )
            text = None
        elif hook_name == "stop":
            hook_commands.stop(ctx)
            text = None
        else:
            text = hook_commands.prompt_submit(ctx)
    except Exception as error:
        sys.stdout.write("guild hook error: {}\n".format(error))
        return 0
    _print(text)
    return 0


def _run_pre_commit_hook():
    try:
        cwd = Path.cwd()
        ctx = _build_context(session_info.current_session_id(), cwd)
        reasons = hook_commands.pre_commit(ctx, hook_commands.staged_paths(cwd))
    except Exception as error:
        sys.stderr.write("guild hook error: {}\n".format(error))
        return 0
    for reason in reasons:
        sys.stderr.write(reason + "\n")
    return 1 if reasons else 0


def _dispatch_hook(args):
    if args.hook_name == "pre-commit":
        return _run_pre_commit_hook()
    raw = sys.stdin.read()
    try:
        stdin_data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        stdin_data = {}
    if args.hook_name == "pre-push":
        return _run_pre_push_hook(stdin_data)
    if args.hook_name == "pre-pr-owner":
        return _run_pre_pr_owner_hook(stdin_data)
    if args.hook_name == "pre-edit":
        return _run_pre_edit_hook(stdin_data)
    return _run_stateful_hook(args.hook_name, stdin_data)


def main(argv):
    os.umask(0o077)
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
