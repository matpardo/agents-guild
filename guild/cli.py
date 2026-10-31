import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

from guild import background, db, due_jobs, notify, origin, paths, pii, session_info, statusline_state, timeutil
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


def _handle_unwire_settings(ctx, args):
    from guild.commands import unwire_settings as unwire_settings_commands

    _print(unwire_settings_commands.run())
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

    _print(party_commands.start(ctx, args.name, args.reason))
    return 0


def _handle_party_resume(ctx, args):
    from guild.commands import party as party_commands

    _print(party_commands.resume(ctx, args.party, args.session, None))
    return 0


def _handle_party_park(ctx, args):
    from guild.commands import party as party_commands

    _print(party_commands.park(ctx, args.name, args.reason))
    return 0


def _handle_party_unpark(ctx, args):
    from guild.commands import party as party_commands

    _print(party_commands.unpark(ctx, args.name))
    return 0


def _handle_party_close(ctx, args):
    from guild import lifecycle
    from guild.commands import party as party_commands

    _print(party_commands.close(ctx, args.name, args.force, args.pending, lifecycle.run_process))
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

    _print(
        quest_commands.add(
            ctx,
            args.slug,
            args.title,
            args.epic,
            args.tasks,
            args.titles,
            args.no_epic,
            args.followups_of,
            args.open,
            args.reason,
        )
    )
    return 0


def _handle_quest_take(ctx, args):
    from guild.commands import quest as quest_commands

    _print(quest_commands.take(ctx, args.slug))
    return 0


def _handle_quest_release(ctx, args):
    from guild.commands import quest as quest_commands

    _print(quest_commands.release(ctx, args.slug))
    return 0


def _handle_quest_board(ctx, args):
    from guild.commands import quest_board

    _print_lines(quest_board.board(ctx, args.project))
    return 0


def _handle_task_add(ctx, args):
    from guild.commands import task as task_commands

    quest, tid = args.ref.split("/", 1)
    _print(task_commands.add(ctx, quest, tid, args.title, args.reason))
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


def _handle_task_move(ctx, args):
    from guild.commands import task as task_commands

    quest, tids_csv = args.ref.split("/", 1)
    _print(task_commands.move(ctx, quest, tids_csv, args.to))
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
            args.blocked_external,
            args.no_blocked_external,
            args.task,
            args.card,
        )
    )
    return 0


def _handle_pr_untrack(ctx, args):
    from guild.commands import pr as pr_commands

    _print(pr_commands.untrack(ctx, args.ref))
    return 0


def _handle_pr_ack(ctx, args):
    from guild.commands import pr as pr_commands

    _print(pr_commands.ack_comments(ctx, args.ref))
    return 0


def _handle_pr_ready_check(ctx, args):
    from guild import lifecycle, refs
    from guild.commands import pr as pr_commands
    from guild.commands import sync as sync_commands

    repo, number = refs.parse_pr_ref(args.ref)
    failures = sync_commands.refresh_pr(ctx, repo, number, lifecycle.run_process)
    lines, exit_code = pr_commands.ready_check(ctx, args.ref, bool(failures))
    _print_lines(lines)
    return exit_code


_DEFAULT_WAIT_TIMEOUT = "2h"


def _handle_ask_wait(ctx, args):
    from guild.commands import ask as ask_commands

    if args.context is not None or args.ref or args.option:
        raise GuildError("`guild ask wait` takes only an id and --timeout", 1)
    if not args.wait_id.isdigit():
        raise GuildError("ask id '{}' must be an integer".format(args.wait_id), 1)
    timeout = timeutil.parse_duration(_DEFAULT_WAIT_TIMEOUT if args.timeout is None else args.timeout)
    line, exit_code = ask_commands.wait(ctx.conn, int(args.wait_id), timeout, time.sleep, timeutil.utcnow)
    _print(line)
    return exit_code


def _handle_ask(ctx, args):
    from guild.commands import ask as ask_commands

    if args.question == "wait" and args.wait_id is not None:
        return _handle_ask_wait(ctx, args)
    if args.wait_id is not None:
        raise GuildError("unexpected extra argument '{}'".format(args.wait_id), 1)
    if args.context is None:
        raise GuildError("--context is required", 1)
    if args.timeout is not None:
        raise GuildError("--timeout only applies to ask wait", 1)
    _print(ask_commands.create(ctx, args.question, args.context, args.ref or [], args.option or []))
    return 0


def _handle_pr_wait(ctx, args):
    from guild.commands import pr as pr_commands

    key = background.pr_key(os.getpid())
    if ctx.session_id is not None:
        background.mark(ctx.state_dir, ctx.session_id, key, "pr {}".format(args.ref))
    try:
        line, exit_code = pr_commands.wait(
            ctx.conn,
            args.ref,
            timeutil.parse_duration(args.timeout),
            time.sleep,
            timeutil.utcnow,
            lambda: due_jobs.spawn_due(ctx.state_dir, ctx.cwd, time.time(), due_jobs.spawn_detached),
        )
    finally:
        if ctx.session_id is not None:
            background.clear(ctx.state_dir, ctx.session_id, key)
    _print(line)
    return exit_code


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
    _print_lines(board_commands.render_all_asks(ctx, args.party, since_cutoff, _stdout_is_colored(), _terminal_width()))
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


def _handle_idea_add(ctx, args):
    from guild.commands import idea as idea_commands

    _print(idea_commands.add(ctx, args.title, args.description, args.requester, args.deadline, args.project))
    return 0


def _idea_edit_fields(args):
    fields = {
        name: getattr(args, name)
        for name in ("title", "description", "requester", "deadline", "project")
        if getattr(args, name) is not None
    }
    for name in ("requester", "deadline", "project"):
        if getattr(args, "no_" + name):
            fields[name] = None
    return fields


def _handle_idea_edit(ctx, args):
    from guild.commands import idea as idea_commands

    _print(idea_commands.edit(ctx, args.id, _idea_edit_fields(args)))
    return 0


def _handle_idea_delete(ctx, args):
    from guild.commands import idea as idea_commands

    _print(idea_commands.delete(ctx, args.id))
    return 0


def _handle_idea_link(ctx, args):
    from guild.commands import idea as idea_commands

    _print(idea_commands.link(ctx, args.id, args.party))
    return 0


def _handle_idea_unlink(ctx, args):
    from guild.commands import idea as idea_commands

    _print(idea_commands.unlink(ctx, args.id, args.party))
    return 0


def _handle_ideas(ctx, args):
    from guild.commands import idea as idea_commands

    if args.idea_id is not None:
        if args.project is not None:
            raise GuildError("guild ideas <id> takes no filters", 1)
        _print_lines(idea_commands.show(ctx, args.idea_id))
        return 0
    _print_lines(idea_commands.list_ideas(ctx, args.project))
    return 0


def _handle_adventurer_start(ctx, args):
    from guild.commands import adventurer as adventurer_commands

    _print(adventurer_commands.start(ctx, args.job, args.task, args.health_job, args.reason))
    return 0


def _handle_adventurer_promote(ctx, args):
    from guild.commands import adventurer as adventurer_commands

    _print(adventurer_commands.promote(ctx, args.party, args.reason))
    return 0


def _handle_adventurer_launch(ctx, args):
    from guild import tmux_windows
    from guild.commands import adventurer as adventurer_commands

    _print(adventurer_commands.launch(ctx, args.name, tmux_windows.Tmux()))
    return 0


def _handle_adventurer_done(ctx, args):
    from guild import lifecycle
    from guild.commands import adventurer as adventurer_commands

    _print(adventurer_commands.done(ctx, args.pending, lifecycle.run_process))
    return 0


def _handle_adventurer_dismiss(ctx, args):
    from guild.commands import adventurer as adventurer_commands

    _print(adventurer_commands.dismiss(ctx, args.id))
    return 0


def _handle_adventurers(ctx, args):
    from guild.commands import adventurer as adventurer_commands

    if args.adventurer_id is not None:
        _print_lines(adventurer_commands.show(ctx, args.adventurer_id))
        return 0
    _print_lines(adventurer_commands.list_adventurers(ctx))
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


def _claim_line(row):
    line = "{} — {} until {}".format(row["area"], row["party"], row["expires_at"])
    dates = timeutil.dates_label(row["created_at"], row["updated_at"])
    if dates is None:
        return line
    return "{} ({})".format(line, dates)


def _handle_claims(ctx, args):
    from guild.commands import claim as claim_commands

    rows = claim_commands.list_claims(ctx.conn, ctx.now)
    _print_lines([_claim_line(row) for row in rows])
    return 0


def _handle_memory_add(ctx, args):
    from guild.commands import memory as memory_commands

    _print(memory_commands.add(ctx, args.text))
    return 0


def _handle_memory_list(ctx, args):
    from guild import pii
    from guild.commands import memory as memory_commands

    items = memory_commands.all_items(args.party)
    _print_lines(
        [
            "{}: {}{}".format(
                item["id"],
                item["text"],
                "  " + pii.INSTRUCTION_LIKE_FLAG if memory_commands.flagged(item["text"]) else "",
            )
            for item in items
        ]
    )
    return 0


def _handle_memory_rm(ctx, args):
    from guild.commands import memory as memory_commands

    _print(memory_commands.rm(ctx, args.item_id))
    return 0


def _handle_realm_init(ctx, args):
    from guild.commands import realm as realm_commands

    _print(realm_commands.init(args.name, args.bind, args.port, os.environ.get("CLAUDECODE")))
    return 0


def _handle_realm_serve(ctx, args):
    from guild.commands import realm as realm_commands

    return realm_commands.serve(os.environ.get("CLAUDECODE"))


def _handle_realm_member_add(ctx, args):
    from guild.commands import realm as realm_commands

    _print(realm_commands.member_add(args.name, os.environ.get("CLAUDECODE")))
    return 0


def _handle_realm_member_list(ctx, args):
    from guild.commands import realm as realm_commands

    _print_lines(realm_commands.member_list(os.environ.get("CLAUDECODE")))
    return 0


def _handle_realm_member_remove(ctx, args):
    from guild.commands import realm as realm_commands

    _print(realm_commands.member_remove(args.name, os.environ.get("CLAUDECODE")))
    return 0


def _handle_realm_join(ctx, args):
    from guild.commands import realm as realm_commands

    _print(realm_commands.join(args.url, args.fingerprint, args.force, os.environ.get("CLAUDECODE")))
    return 0


def _handle_realm_push(ctx, args):
    from guild.commands import realm as realm_commands

    _print(realm_commands.push(ctx, os.environ.get("CLAUDECODE")))
    return 0


def _handle_realm_status(ctx, args):
    from guild.commands import realm as realm_commands

    _print(realm_commands.show_status(ctx, args.cached))
    return 0


def _handle_realm_doctor(ctx, args):
    from guild.commands import realm as realm_commands

    lines = realm_commands.doctor_lines(ctx)
    _print_lines([line for _, line in lines])
    return 0 if all(passed for passed, _ in lines) else 1


def _handle_realm_send(ctx, args):
    from guild.commands import realm as realm_commands

    _print(realm_commands.send(args.guild, args.file, os.environ.get("CLAUDECODE")))
    return 0


def _handle_realm_inbox(ctx, args):
    from guild.commands import realm as realm_commands

    model = realm_commands.inbox_model(ctx, os.environ.get("CLAUDECODE"))
    _print(realm_commands.render_inbox(model, ctx.now))
    return 0


def _handle_realm_fetch(ctx, args):
    from guild.commands import realm as realm_commands

    _print(realm_commands.render_fetch(realm_commands.fetch(args.id, args.out, os.environ.get("CLAUDECODE"))))
    return 0


def _handle_realm_drop(ctx, args):
    from guild.commands import realm as realm_commands

    _print(realm_commands.drop(args.id, os.environ.get("CLAUDECODE")))
    return 0


def _handle_raid_join(ctx, args):
    from guild.commands import raid as raid_commands

    _print(raid_commands.join(ctx, args.name, args.ttl, args.until_leave))
    return 0


def _handle_raid_leave(ctx, args):
    from guild.commands import raid as raid_commands

    _print(raid_commands.leave(ctx, args.name))
    return 0


def _handle_base_pause(ctx, args):
    from guild.commands import base_pause as base_pause_commands

    _print(base_pause_commands.pause(ctx, args.repo))
    return 0


def _handle_base_resume(ctx, args):
    from guild.commands import base_pause as base_pause_commands

    _print(base_pause_commands.resume(ctx, args.repo))
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

    if args.head:
        _print(merge_queue_commands.head_line(ctx, args.raid, args.party))
        return 0
    _print_lines(merge_queue_commands.run(ctx, args.raid, args.party))
    return 0


def _handle_review_md(ctx, args):
    from guild.commands import merge_queue as merge_queue_commands

    _print_lines(merge_queue_commands.review_md(ctx, args.raid, args.party))
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

    _print_lines(board_commands.render_board(ctx, args.party, args.raid, _stdout_is_colored(), _terminal_width()))
    return 0


def _handle_handoff(ctx, args):
    from guild import tmux_windows
    from guild.commands import handoff as handoff_commands

    if args.party is not None:
        provided = (
            ("prune", args.action is not None),
            ("--in-flight", args.in_flight is not None),
            ("--learned", args.learned is not None),
            ("--parked", args.parked is not None),
            ("--model", args.model is not None),
            ("--dry-run", args.dry_run),
            ("--respawn", args.respawn),
            ("--close", args.close),
        )
        for flag, given in provided:
            if given:
                raise GuildError("--party cannot be combined with {}".format(flag), 1)
        if ctx.session_id is not None:
            raise GuildError("--party cannot be used from inside a Claude Code session", 1)
        _print(handoff_commands.run_for_party(ctx, args.party))
        return 0
    if args.action == "prune":
        provided = (
            ("--in-flight", args.in_flight is not None),
            ("--learned", args.learned is not None),
            ("--parked", args.parked is not None),
            ("--model", args.model is not None),
            ("--respawn", args.respawn),
            ("--close", args.close),
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
        ctx,
        args.in_flight,
        args.learned,
        args.parked,
        args.model,
        args.respawn,
        args.close,
        tmux,
        os.environ.get("TMUX_PANE"),
        time.sleep,
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
        statusline_state.record_ctx(ctx.state_dir, args.session, args.ctx)
        statusline_state.record_baseline_once(ctx.state_dir, args.session, args.ctx)
    _print(statusline_commands.render(ctx, args.session))
    return 0


def _handle_seed(ctx, args):
    from guild.commands import seed as seed_commands

    _print(seed_commands.run(ctx, args.file))
    return 0


def _handle_compact(ctx, args):
    from guild.commands import compact as compact_commands

    _print(compact_commands.run(ctx, args.dry_run))
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
    parser = subparsers.add_parser("party", help="start, resume or close a party")
    actions = parser.add_subparsers(dest="party_action", required=True, metavar="<subcommand>")

    start = actions.add_parser("start", help="start a party and bind this session to it")
    start.add_argument("name")
    start.add_argument("--reason", required=True, help="why this work is a party")
    start.set_defaults(handler=_handle_party_start)

    resume = actions.add_parser("resume", help="resume a party in this session")
    resume.add_argument("party")
    resume.add_argument("--session", help="session name; from a human terminal only")
    resume.set_defaults(handler=_handle_party_resume)

    park = actions.add_parser("park", help="mark a party as waiting on something outside development")
    park.add_argument("name")
    park.add_argument("--reason", required=True, help="what the party waits on")
    park.set_defaults(handler=_handle_party_park)

    unpark = actions.add_parser("unpark", help="clear the parked mark of a party")
    unpark.add_argument("name")
    unpark.set_defaults(handler=_handle_party_unpark)

    close = actions.add_parser(
        "close", help="close a party; refuses while quests are unfinished or asks or PRs are open unless --force"
    )
    close.add_argument("name", nargs="?")
    close.add_argument("--force", action="store_true", help="close despite unfinished quests, open asks or open PRs")
    close.add_argument("--pending", required=True, help="what is left pending; 'none' if nothing")
    close.set_defaults(handler=_handle_party_close)


def _add_quest_parser(subparsers):
    parser = subparsers.add_parser("quest", help="add, take, release or finish quests, and list the quest board")
    actions = parser.add_subparsers(dest="quest_action", required=True, metavar="<subcommand>")

    add = actions.add_parser("add", help="add a quest, optionally with tasks")
    add.add_argument("slug")
    add.add_argument("--title", required=True)
    add.add_argument("--epic", help="epic slug the quest belongs to")
    add.add_argument("--tasks", help="comma-separated task ids")
    add.add_argument("--titles", help="comma-separated titles, one per task")
    add.add_argument("--no-epic", action="store_true", help="create a quest outside any epic")
    add.add_argument("--followups-of", help="quest this one follows up")
    add.add_argument("--open", action="store_true", help="create an open quest no party owns yet")
    add.add_argument("--reason", help="why the quest was added")
    add.set_defaults(handler=_handle_quest_add)

    take = actions.add_parser("take", help="take an open quest of your project for your party")
    take.add_argument("slug")
    take.set_defaults(handler=_handle_quest_take)

    release = actions.add_parser("release", help="return a quest with no started task to the quest board")
    release.add_argument("slug")
    release.set_defaults(handler=_handle_quest_release)

    board = actions.add_parser("board", help="list open quests and the SDD tasks no quest covers")
    board.add_argument("--project", help="project to list; default is the project of the current directory")
    board.set_defaults(handler=_handle_quest_board)

    done = actions.add_parser("done", help="mark a quest done; refuses while tasks are not done unless --force")
    done.add_argument("slug")
    done.add_argument("--accept-drift", action="store_true", help="finish despite epic drift and record it")
    done.add_argument("--force", action="store_true", help="finish despite tasks not done")
    done.set_defaults(handler=_handle_quest_done)

    incomplete = actions.add_parser("incomplete", help="mark a done quest as not really finished")
    incomplete.add_argument("slug")
    incomplete.add_argument("--reason", required=True, help="why the quest was not finished")
    incomplete.set_defaults(handler=_handle_quest_incomplete)


def _add_task_parser(subparsers):
    parser = subparsers.add_parser("task", help="add tasks and change their state")
    actions = parser.add_subparsers(dest="task_action", required=True, metavar="<subcommand>")

    add = actions.add_parser("add", help="add a task to an open quest of your party")
    add.add_argument("ref")
    add.add_argument("--title", required=True)
    add.add_argument("--reason", help="why the task was added")
    add.set_defaults(handler=_handle_task_add)

    start = actions.add_parser("start", help="mark a task in progress")
    start.add_argument("ref")
    start.add_argument("--summary")
    start.set_defaults(handler=_handle_task_start)

    block = actions.add_parser("block", help="mark a task blocked, with a reason")
    block.add_argument("ref")
    block.add_argument("--reason", required=True, help="why the task is blocked")
    block.set_defaults(handler=_handle_task_block)

    done = actions.add_parser("done", help="mark a task done")
    done.add_argument("ref")
    done.add_argument("--summary")
    done.set_defaults(handler=_handle_task_done)

    move = actions.add_parser("move", help="move queued or blocked tasks to another quest of the same epic")
    move.add_argument("ref", help="<quest>/<tid>[,<tid>...]")
    move.add_argument("--to", required=True, help="target quest slug")
    move.set_defaults(handler=_handle_task_move)


def _add_flag_pair(parser, name, dest):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--" + name, dest=dest, action="store_const", const=True)
    group.add_argument("--no-" + name, dest=dest, action="store_const", const=False)


def _handle_finding_record(ctx, args):
    from guild.commands import finding as finding_commands

    _print(finding_commands.record(ctx, args.ref, args.finding_class))
    return 0


def _handle_finding_list(ctx, args):
    from guild.commands import finding as finding_commands

    _print(finding_commands.list_classes(ctx))
    return 0


def _add_finding_parser(subparsers):
    parser = subparsers.add_parser("finding", help="record recurring audit and review findings")
    actions = parser.add_subparsers(dest="finding_action", required=True, metavar="<subcommand>")

    record = actions.add_parser("record", help="count a recurring finding class once for a PR")
    record.add_argument("ref")
    record.add_argument("--class", dest="finding_class", required=True, help="finding class slug")
    record.set_defaults(handler=_handle_finding_record)

    list_parser = actions.add_parser("list", help="list finding classes of the project with PR counts")
    list_parser.set_defaults(handler=_handle_finding_list)


def _add_pr_parser(subparsers):
    parser = subparsers.add_parser("pr", help="track PRs and set their state")
    actions = parser.add_subparsers(dest="pr_action", required=True, metavar="<subcommand>")

    track = actions.add_parser(
        "track",
        help="start tracking a PR against a task (party, adventurer: its own; health job: none), optionally with a card",
    )
    track.add_argument("ref")
    track.add_argument("--task", help="task as <quest>/<tid>")
    track.add_argument("--card", help="tracker card key")
    track.add_argument("--what", required=True, help="one sentence on what the PR does")
    track.add_argument("--waits", required=True, help="what the PR waits on")
    track.add_argument("--needs-human-pr-review", action="store_true", help="PR needs a human review")
    track.add_argument("--fixes-main", action="store_true", help="PR repairs a broken main; first in the queue")
    track.add_argument("--fixes-flaky", action="store_true", help="PR fixes flaky tests; first in the queue")
    track.set_defaults(handler=_handle_pr_track)

    set_parser = actions.add_parser("set", help="change the lifecycle, wait reason or flags of a tracked PR")
    set_parser.add_argument("ref")
    set_parser.add_argument("--lifecycle", choices=["draft", "converging", "ready"], help="PR lifecycle state")
    set_parser.add_argument("--waits", help="what the PR waits on")
    _add_flag_pair(set_parser, "needs-ask-answer", "needs_ask_answer")
    _add_flag_pair(set_parser, "needs-human-pr-review", "needs_human_pr_review")
    _add_flag_pair(set_parser, "fixes-main", "fixes_main")
    _add_flag_pair(set_parser, "fixes-flaky", "fixes_flaky")
    external = set_parser.add_mutually_exclusive_group()
    external.add_argument("--blocked-external", help="block the PR on a decision outside development, with a reason")
    external.add_argument("--no-blocked-external", action="store_true", help="clear the external block")
    set_parser.add_argument("--task", help="relink the PR to this task, as <quest>/<tid>")
    set_parser.add_argument("--card", help="relink the PR to this tracker card key")
    set_parser.set_defaults(handler=_handle_pr_set)

    untrack = actions.add_parser("untrack", help="stop tracking a PR")
    untrack.add_argument("ref")
    untrack.set_defaults(handler=_handle_pr_untrack)

    ack = actions.add_parser("ack", help="mark the review comments of a PR as read")
    ack.add_argument("ref")
    ack.set_defaults(handler=_handle_pr_ack)

    ready_check = actions.add_parser("ready-check", help="refresh a PR and list everything between it and a merge")
    ready_check.add_argument("ref")
    ready_check.set_defaults(handler=_handle_pr_ready_check)

    wait = actions.add_parser("wait", help="block until the PR gets a comment, finishes checks or closes")
    wait.add_argument("ref")
    wait.add_argument("--timeout", default="2h", help="give up after this long, e.g. 30m, 2h (default 2h)")
    wait.set_defaults(handler=_handle_pr_wait)


def _add_notice_parser(subparsers):
    parser = subparsers.add_parser("notice", help="create and manage notices")
    actions = parser.add_subparsers(dest="notice_action", required=True, metavar="<subcommand>")

    create = actions.add_parser("create", help="create a notice for a project, guild or raid")
    create.add_argument("text")
    create.add_argument("--to", required=True, help="project:<name>, guild or raid:<name>")
    create.add_argument("--ttl", required=True, help="lifetime, e.g. 30m, 8h, 3d")
    create.add_argument("--until", help="end on pr:<owner/repo>#<n>:merged or closed")
    create.set_defaults(handler=_handle_notice_create)

    close = actions.add_parser("close", help="close a notice")
    close.add_argument("id", type=int)
    close.set_defaults(handler=_handle_notice_close)

    seen = actions.add_parser("seen", help="mark a notice, or all, as seen")
    seen_target = seen.add_mutually_exclusive_group(required=True)
    seen_target.add_argument("id", type=int, nargs="?")
    seen_target.add_argument("--all", action="store_true", help="mark every notice as seen")
    seen.set_defaults(handler=_handle_notice_seen)

    unseen = actions.add_parser("unseen", help="mark a notice as unseen")
    unseen.add_argument("id", type=int)
    unseen.set_defaults(handler=_handle_notice_unseen)


def _add_idea_parser(subparsers):
    parser = subparsers.add_parser("idea", help="add, edit or delete ideas in the backlog")
    actions = parser.add_subparsers(dest="idea_action", required=True, metavar="<subcommand>")

    add = actions.add_parser("add", help="park an idea")
    add.add_argument("title")
    add.add_argument("--description", required=True)
    add.add_argument("--requester", help="who asked for it")
    add.add_argument("--deadline", help="YYYY-MM-DD")
    add.add_argument("--project", help="registered project the idea belongs to")
    add.set_defaults(handler=_handle_idea_add)

    edit = actions.add_parser("edit", help="change fields of an idea")
    edit.add_argument("id", type=int)
    edit.add_argument("--title")
    edit.add_argument("--description")
    for name in ("requester", "deadline", "project"):
        group = edit.add_mutually_exclusive_group()
        group.add_argument("--" + name)
        group.add_argument("--no-" + name, action="store_true", help="clear the {}".format(name))
    edit.set_defaults(handler=_handle_idea_edit)

    delete = actions.add_parser("delete", help="delete an idea once it became code, spec, card or quest")
    delete.add_argument("id", type=int)
    delete.set_defaults(handler=_handle_idea_delete)

    link = actions.add_parser("link", help="link an idea to the party working on it")
    unlink = actions.add_parser("unlink", help="remove the link between an idea and a party")
    for parser_, handler in ((link, _handle_idea_link), (unlink, _handle_idea_unlink)):
        parser_.add_argument("id", type=int)
        parser_.add_argument("--party", help="required from the human terminal; a session uses its own party")
        parser_.set_defaults(handler=handler)


def _add_adventurer_parser(subparsers):
    parser = subparsers.add_parser("adventurer", help="start or finish a one-job session")
    actions = parser.add_subparsers(dest="adventurer_action", required=True, metavar="<subcommand>")

    start = actions.add_parser("start", help="register this session as an adventurer")
    start.add_argument("job", nargs="?", help="what this session does; omit with --job")
    start.add_argument(
        "--task",
        help="required without --job: <epic>/<tid> (synced, or new in a synced epic) or <quest>/<tid> of a no-epic open quest",
    )
    start.add_argument("--job", dest="health_job", help="health job of the project config, instead of a job text")
    start.add_argument("--reason", required=True, help="why this work is an adventurer")
    start.set_defaults(handler=_handle_adventurer_start)

    promote = actions.add_parser("promote", help="turn this adventurer into a party led by this session")
    promote.add_argument("party")
    promote.add_argument("--reason", required=True, help="why the work outgrew one job")
    promote.set_defaults(handler=_handle_adventurer_promote)

    launch = actions.add_parser("launch", help="open a tmux window running a health job (human terminal only)")
    launch.add_argument("name", help="health job name")
    launch.set_defaults(handler=_handle_adventurer_launch)

    done = actions.add_parser("done", help="end the adventurer and report what is pending")
    done.add_argument("--pending", required=True, help="what is left to do, or none")
    done.set_defaults(handler=_handle_adventurer_done)

    dismiss = actions.add_parser("dismiss", help="remove a done adventurer from the board")
    dismiss.add_argument("id", type=int)
    dismiss.set_defaults(handler=_handle_adventurer_dismiss)


def _add_realm_parser(subparsers):
    parser = subparsers.add_parser("realm", help="run a realm hub, join one and see every guild's status")
    actions = parser.add_subparsers(dest="realm_action", required=True, metavar="<subcommand>")

    init = actions.add_parser("init", help="create the hub config and a pinned self-signed certificate")
    init.add_argument("--name", required=True)
    init.add_argument("--bind", required=True)
    init.add_argument("--port", type=int, required=True)
    init.set_defaults(handler=_handle_realm_init)

    serve = actions.add_parser("serve", help="serve the realm hub over https")
    serve.set_defaults(handler=_handle_realm_serve)

    join = actions.add_parser("join", help="join a realm hub (token is read from the prompt)")
    join.add_argument("url")
    join.add_argument("--fingerprint", required=True)
    join.add_argument("--force", action="store_true")
    join.set_defaults(handler=_handle_realm_join)

    push = actions.add_parser("push", help="send this guild's counts to the realm hub")
    push.set_defaults(handler=_handle_realm_push)

    send = actions.add_parser("send", help="send an md file to another guild's inbox")
    send.add_argument("guild")
    send.add_argument("file")
    send.set_defaults(handler=_handle_realm_send)

    inbox = actions.add_parser("inbox", help="list the files waiting in this guild's realm inbox")
    inbox.set_defaults(handler=_handle_realm_inbox)

    fetch = actions.add_parser("fetch", help="save an inbox file to disk for you to read first")
    fetch.add_argument("id")
    fetch.add_argument("--out", default=str(paths.realm_files_dir()), help="directory to save into")
    fetch.set_defaults(handler=_handle_realm_fetch)

    drop = actions.add_parser("drop", help="delete a file from the realm inbox")
    drop.add_argument("id")
    drop.set_defaults(handler=_handle_realm_drop)

    realm_status = actions.add_parser("status", help="show every guild's counts")
    realm_status.add_argument("--cached", action="store_true", help="print the last fetched status without network")
    realm_status.set_defaults(handler=_handle_realm_status)

    realm_doctor = actions.add_parser("doctor", help="check the link to the realm hub and the hub itself")
    realm_doctor.set_defaults(handler=_handle_realm_doctor)

    member = actions.add_parser("member", help="add, list or remove hub members")
    member_actions = member.add_subparsers(dest="member_action", required=True, metavar="<subcommand>")

    member_add = member_actions.add_parser("add", help="add a member and print its token once")
    member_add.add_argument("name")
    member_add.set_defaults(handler=_handle_realm_member_add)

    member_list = member_actions.add_parser("list", help="list member names")
    member_list.set_defaults(handler=_handle_realm_member_list)

    member_remove = member_actions.add_parser("remove", help="remove a member and its status")
    member_remove.add_argument("name")
    member_remove.set_defaults(handler=_handle_realm_member_remove)


def _add_memory_parser(subparsers):
    parser = subparsers.add_parser("memory", help="add, list or remove items in a party's memory")
    actions = parser.add_subparsers(dest="memory_action", required=True, metavar="<subcommand>")

    add = actions.add_parser("add", help="add a memory item for your bound party")
    add.add_argument("text")
    add.set_defaults(handler=_handle_memory_add)

    list_parser = actions.add_parser("list", help="list memory items")
    list_parser.add_argument("--party", help="only this party")
    list_parser.set_defaults(handler=_handle_memory_list)

    rm = actions.add_parser("rm", help="remove a memory item")
    rm.add_argument("item_id")
    rm.set_defaults(handler=_handle_memory_rm)


def _add_raid_parser(subparsers):
    parser = subparsers.add_parser("raid", help="join, leave, pause or resume a raid")
    actions = parser.add_subparsers(dest="raid_action", required=True, metavar="<subcommand>")

    join = actions.add_parser("join", help="join a raid")
    join.add_argument("name")
    join_mode = join.add_mutually_exclusive_group(required=True)
    join_mode.add_argument("--ttl", help="membership lifetime, e.g. 8h")
    join_mode.add_argument("--until-leave", action="store_true", help="stay until raid leave or party close")
    join.set_defaults(handler=_handle_raid_join)

    leave = actions.add_parser("leave", help="leave a raid")
    leave.add_argument("name")
    leave.set_defaults(handler=_handle_raid_leave)

    pause = actions.add_parser("pause", help="ask every member party of a raid to stop")
    pause.add_argument("name")
    pause.set_defaults(handler=_handle_raid_pause)

    resume = actions.add_parser("resume", help="lift a raid pause")
    resume.add_argument("name")
    resume.set_defaults(handler=_handle_raid_resume)


def _add_base_parser(subparsers):
    parser = subparsers.add_parser("base", help="pause or resume the bases fetch of a repo")
    actions = parser.add_subparsers(dest="base_action", required=True, metavar="<subcommand>")

    pause = actions.add_parser("pause", help="stop fetching the base of a repo")
    pause.add_argument("repo", help="owner/repo")
    pause.set_defaults(handler=_handle_base_pause)

    resume = actions.add_parser("resume", help="fetch the base of a repo again")
    resume.add_argument("repo", help="owner/repo")
    resume.set_defaults(handler=_handle_base_resume)


def _add_merge_queue_parser(subparsers):
    parser = subparsers.add_parser("merge-queue", help="read-only: PRs in the order to merge by hand")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--raid", help="only PRs of this raid")
    scope.add_argument("--party", help="only PRs of this party")
    parser.add_argument("--head", action="store_true", help="print only the PR to merge now")
    parser.set_defaults(handler=_handle_merge_queue)
    actions = parser.add_subparsers(dest="merge_queue_action", required=False, metavar="<subcommand>")

    pin = actions.add_parser("pin", help="pin a PR to merge before another")
    pin.add_argument("ref")
    pin.add_argument("--before", required=True, help="PR that must merge after")
    pin.set_defaults(handler=_handle_merge_queue_pin)

    unpin = actions.add_parser("unpin", help="remove a merge order pin")
    unpin.add_argument("ref")
    unpin.add_argument("--before", required=True, help="PR the pin was before")
    unpin.set_defaults(handler=_handle_merge_queue_unpin)


def _add_review_md_parser(subparsers):
    parser = subparsers.add_parser("review-md", help="read-only: markdown list of the PRs ready for the person")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--raid", help="only PRs of this raid")
    scope.add_argument("--party", help="only PRs of this party")
    parser.set_defaults(handler=_handle_review_md)


def _add_main_parser(subparsers):
    parser = subparsers.add_parser("main", help="mark a repo main branch red or green by hand")
    actions = parser.add_subparsers(dest="main_action", required=True, metavar="<subcommand>")

    red = actions.add_parser("red", help="mark a repo main branch red")
    red.add_argument("repo")
    red.add_argument("--reason", required=True, help="why main is red")
    red.set_defaults(handler=_handle_main_red)

    green = actions.add_parser("green", help="clear the manual red mark")
    green.add_argument("repo")
    green.set_defaults(handler=_handle_main_green)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="guild",
        description="Guild coordinates parallel Claude Code sessions. See the README Commands section for the full reference.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    whoami = subparsers.add_parser("whoami", help="show the session, party and project you are bound to")
    whoami.set_defaults(handler=_handle_whoami)

    doctor = subparsers.add_parser(
        "doctor", help="read-only checks of hooks, permission rules, GUILD.md and project configs"
    )
    doctor.add_argument("--scan-prs", action="store_true", help="scan open PRs for guild traces through gh")
    doctor.set_defaults(handler=_handle_doctor)

    wire_settings = subparsers.add_parser(
        "wire-settings", help="merge guild hooks and permission rules into ~/.claude/settings.json"
    )
    wire_settings.set_defaults(handler=_handle_wire_settings)

    unwire_settings = subparsers.add_parser(
        "unwire-settings", help="remove guild hooks and permission rules from ~/.claude/settings.json"
    )
    unwire_settings.set_defaults(handler=_handle_unwire_settings)

    init_project = subparsers.add_parser("init-project", help="create a project config from a JSON file")
    init_project.add_argument("name")
    init_project.add_argument("--config", required=True, help="path of the project config JSON")
    init_project.set_defaults(handler=_handle_init_project)

    _add_party_parser(subparsers)
    _add_quest_parser(subparsers)
    _add_task_parser(subparsers)
    _add_pr_parser(subparsers)
    _add_finding_parser(subparsers)

    ask = subparsers.add_parser("ask", help="ask the human a decision")
    ask.add_argument(
        "question", help="at most {} characters; put details in --context".format(pii.ASK_QUESTION_MAX_LENGTH)
    )
    ask.add_argument("wait_id", nargs="?", help="ask id, with `guild ask wait <id>`")
    ask.add_argument(
        "--context", help="short context for the human, at most {} characters".format(pii.ASK_CONTEXT_MAX_LENGTH)
    )
    ask.add_argument("--timeout", help="with ask wait: give up after this long (default 2h)")
    ask.add_argument("--ref", action="append", help="pr:<owner/repo>#<n>, task:<quest>/<tid> or card:<KEY>; repeatable")
    ask.add_argument("--option", action="append", help="an answer option; repeatable")
    ask.set_defaults(handler=_handle_ask)

    answer = subparsers.add_parser("answer", help="answer an open ask")
    answer.add_argument("id", type=int)
    answer.add_argument("text")
    answer.set_defaults(handler=_handle_answer)

    dismiss = subparsers.add_parser("dismiss", help="dismiss an open ask")
    dismiss.add_argument("id", type=int)
    dismiss.set_defaults(handler=_handle_dismiss)

    asks = subparsers.add_parser("asks", help="list open asks, or show one in detail")
    asks.add_argument("ask_id", type=int, nargs="?")
    asks.add_argument("--all", action="store_true", help="include answered and dismissed asks")
    asks.add_argument("--answered", action="store_true", help="list answered asks")
    asks.add_argument("--page", type=int, help="page number of answered asks")
    asks.add_argument("--party", help="only asks of this party")
    asks.add_argument("--since", help="only asks created within this duration, e.g. 3d")
    asks.set_defaults(handler=_handle_asks)

    _add_notice_parser(subparsers)

    notices = subparsers.add_parser("notices", help="list notices addressed to you")
    notices.set_defaults(handler=_handle_notices)

    _add_idea_parser(subparsers)

    ideas = subparsers.add_parser("ideas", help="list ideas, or show one in detail")
    ideas.add_argument("idea_id", type=int, nargs="?")
    ideas.add_argument("--project", help="only ideas of this project")
    ideas.set_defaults(handler=_handle_ideas)

    _add_adventurer_parser(subparsers)

    adventurers = subparsers.add_parser("adventurers", help="list adventurers, or show one in detail")
    adventurers.add_argument("adventurer_id", type=int, nargs="?")
    adventurers.set_defaults(handler=_handle_adventurers)

    claim = subparsers.add_parser("claim", help="claim a shared area or task, or check a claim")
    claim.add_argument("area")
    claim.add_argument("check_area", nargs="?")
    claim.add_argument("--ttl", help="claim lifetime, e.g. 8h")
    claim.set_defaults(handler=_handle_claim)

    release = subparsers.add_parser("release", help="release a claimed area")
    release.add_argument("area")
    release.set_defaults(handler=_handle_release)

    claims = subparsers.add_parser("claims", help="list active claims")
    claims.set_defaults(handler=_handle_claims)

    _add_memory_parser(subparsers)

    _add_realm_parser(subparsers)

    _add_raid_parser(subparsers)
    _add_base_parser(subparsers)

    raids = subparsers.add_parser("raids", help="list raids")
    raids.set_defaults(handler=_handle_raids)

    _add_merge_queue_parser(subparsers)
    _add_review_md_parser(subparsers)
    _add_main_parser(subparsers)

    board = subparsers.add_parser("board", help="show the human board")
    board_filter = board.add_mutually_exclusive_group()
    board_filter.add_argument("--party", help="only this party")
    board_filter.add_argument("--raid", help="only this raid")
    board.set_defaults(handler=_handle_board)

    history = subparsers.add_parser("history", help="read-only: quests, raids and totals over time")
    history.add_argument("--party", help="only this party")
    history.add_argument("--raid", help="only this raid")
    history.add_argument("--project", help="only this project")
    history.set_defaults(handler=_handle_history)

    cost = subparsers.add_parser("cost", help="token usage from Claude Code transcripts")
    cost.add_argument("--since", default=None, help="only usage within this duration, e.g. 3d")
    cost.add_argument(
        "--by",
        choices=("session", "party", "model", "quest", "task"),
        default="session",
        help="group usage by this field",
    )
    cost.add_argument("--project", default=None, help="only this project")
    cost.set_defaults(handler=_handle_cost)

    next_parser = subparsers.add_parser("next", help="show the next action for your party")
    next_parser.add_argument("--all", action="store_true", help="show the full queue without changing state")
    next_parser.set_defaults(handler=_handle_next)

    handoff = subparsers.add_parser("handoff", help="write the resume state for a fresh session, or prune old handoffs")
    handoff.add_argument("action", nargs="?", choices=["prune"], help="prune: delete old handoff files")
    handoff.add_argument("--in-flight", help="work still running")
    handoff.add_argument("--learned", help="what the next session should know")
    handoff.add_argument("--parked", help="what the party waits on outside development; the board shows it as parked")
    handoff.add_argument("--model", help="model for the next session")
    handoff.add_argument("--dry-run", action="store_true", help="with prune: list what would be deleted")
    handoff.add_argument("--respawn", action="store_true", help="launch the next session in a new tmux window")
    handoff.add_argument("--close", action="store_true", help="close this pane if it is the window guild launched")
    handoff.add_argument("--party", help="hand off a party whose leader session is gone (terminal only)")
    handoff.set_defaults(handler=_handle_handoff)

    sync = subparsers.add_parser("sync", help="refresh state from GitHub, the SDD or the tracker")
    sync.add_argument("--source", required=True, choices=["gh", "sdd", "tracker", "bases"], help="what to refresh from")
    sync.add_argument("--all-projects", action="store_true", help="every project config (sdd and tracker)")
    sync.set_defaults(handler=_handle_sync)

    lifecycle_parser = subparsers.add_parser("lifecycle", help="run project lifecycle commands")
    lifecycle_actions = lifecycle_parser.add_subparsers(dest="lifecycle_action", required=True, metavar="<subcommand>")
    lifecycle_run = lifecycle_actions.add_parser("run", help="run a project lifecycle command by hand")
    lifecycle_run.add_argument("event", choices=["on_pr_merged", "on_pr_closed"])
    lifecycle_run.add_argument("--repo", help="owner/repo to run for")
    lifecycle_run.add_argument("--dry-run", action="store_true", help="show what would run")
    lifecycle_run.set_defaults(handler=_handle_lifecycle_run)

    resources = subparsers.add_parser("resources", help="read-only: what each project costs the machine in disk")
    resources.add_argument("--project", help="only this project")
    resources.add_argument("--since", default="1d", help="growth window, e.g. 1d")
    resources.set_defaults(handler=_handle_resources)
    resources_actions = resources.add_subparsers(dest="resources_action", required=False, metavar="<subcommand>")
    resources_actions.add_parser("collect", help="measure and record disk usage per project")

    compact = subparsers.add_parser(
        "compact", help="back up the database, then drop duplicate sync events and old resource samples"
    )
    compact.add_argument("--dry-run", action="store_true", help="list what would be deleted; no backup, no changes")
    compact.set_defaults(handler=_handle_compact)

    drift = subparsers.add_parser("drift", help="check SDD drift of epics")
    drift_scope = drift.add_mutually_exclusive_group()
    drift_scope.add_argument("--epic", help="check this epic")
    drift_scope.add_argument("--all", action="store_true", help="check every epic")
    drift.set_defaults(handler=_handle_drift)

    revive = subparsers.add_parser("revive", help="relaunch active parties after a reboot")
    revive.add_argument("--party", action="append", default=[], help="relaunch this party; repeatable")
    revive.add_argument("--all", action="store_true", help="relaunch every active party")
    revive.add_argument("--list", action="store_true", help="print copy-paste commands instead of launching")
    revive.set_defaults(handler=_handle_revive)

    brief = subparsers.add_parser("brief", help="show the per-session view, or a budgeted brief for a task")
    brief.add_argument("task", nargs="?")
    brief.set_defaults(handler=_handle_brief)

    inbox = subparsers.add_parser("inbox", help="show events since you last looked")
    inbox.add_argument("--since-last", action="store_true", help="only events since the last call")
    inbox.set_defaults(handler=_handle_inbox)

    statusline = subparsers.add_parser("statusline", help="internal: statusline text for Claude Code")
    statusline.add_argument("--session", required=True, help="session id")
    statusline.add_argument("--ctx", type=int, help="context used, percent")
    statusline.set_defaults(handler=_handle_statusline)

    hook = subparsers.add_parser("hook", help="internal: Claude Code and git hook entry points")
    hook.add_argument(
        "hook_name",
        choices=[
            "session-start",
            "prompt-submit",
            "pre-push",
            "pre-pr-owner",
            "pre-answer",
            "post-tool-use",
            "pre-edit",
            "pre-commit",
            "notification",
            "stop",
            "subagent-start",
            "subagent-stop",
            "pre-compact",
        ],
    )

    seed = subparsers.add_parser("seed", help="internal: load state from a JSON file")
    seed.add_argument("file")
    seed.set_defaults(handler=_handle_seed)

    rebuild = subparsers.add_parser("rebuild", help="internal: rebuild projections from the event log")
    rebuild.set_defaults(handler=_handle_rebuild)

    export = subparsers.add_parser("export", help="export guild-visible data")
    export.add_argument("--visibility", required=True, choices=["guild"], help="visibility to export")
    export.set_defaults(handler=_handle_export)

    web = subparsers.add_parser("web", help="serve the local board in a browser")
    web.add_argument("--port", type=int, default=8765, help="port to listen on")
    web.set_defaults(handler=_handle_web)

    return parser


def _nearest_existing_dir(path):
    while not path.is_dir() and path != path.parent:
        path = path.parent
    return path


def _current_dir():
    try:
        return Path.cwd()
    except FileNotFoundError:
        shell_pwd = os.environ.get("PWD")
        if not shell_pwd:
            raise GuildError("the current directory was deleted and PWD is not set", 1) from None
        return _nearest_existing_dir(Path(shell_pwd))


def _hook_cwd(stdin_data):
    stdin_cwd = stdin_data.get("cwd")
    if stdin_cwd is None:
        return _current_dir()
    return _nearest_existing_dir(Path(stdin_cwd))


def _build_context(session_id, cwd):
    conn = db.connect(paths.db_path())
    paths.ensure_private_dir(paths.state_dir())
    paths.ensure_private_dir(paths.handoffs_dir())
    paths.ensure_private_dir(paths.projects_config_dir())
    paths.ensure_private_dir(paths.memory_dir())
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
        cwd = _hook_cwd(stdin_data)
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
        cwd = _hook_cwd(stdin_data)
        ctx = _build_context(stdin_data.get("session_id"), cwd)
        result = hook_commands.pre_pr_owner(ctx, command)
    except Exception as error:
        sys.stdout.write(json.dumps({"systemMessage": "guild hook error: {}".format(error)}) + "\n")
        return 0
    if result is not None:
        sys.stdout.write(json.dumps(result) + "\n")
    return 0


def _run_pre_answer_hook(stdin_data):
    try:
        command = stdin_data.get("tool_input", {}).get("command", "")
        result = hook_commands.pre_answer(command)
    except Exception as error:
        result = hook_commands.deny_result("guild hook error: {}".format(error))
    if result is not None:
        sys.stdout.write(json.dumps(result) + "\n")
    return 0


def _run_pre_edit_hook(stdin_data):
    try:
        session_id = stdin_data.get("session_id")
        cwd = _hook_cwd(stdin_data)
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
        cwd = _hook_cwd(stdin_data)
        ctx = _build_context(session_id, cwd)
        if hook_name == "session-start":
            text = hook_commands.session_start(
                ctx,
                os.environ.get("GUILD_RESUME") or None,
                os.environ.get("GUILD_ADVENTURER_JOB") or None,
                stdin_data.get("permission_mode"),
                stdin_data.get("source"),
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
        elif hook_name == "subagent-start":
            hook_commands.subagent_start(ctx, stdin_data.get("agent_id"), stdin_data.get("transcript_path"))
            text = None
        elif hook_name == "subagent-stop":
            hook_commands.subagent_stop(ctx, stdin_data.get("agent_id"))
            text = None
        elif hook_name == "pre-compact":
            hook_commands.pre_compact(ctx)
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
        cwd = _current_dir()
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
    if args.hook_name == "pre-answer":
        return _run_pre_answer_hook(stdin_data)
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
        ctx = _build_context(session_info.current_session_id(), _current_dir())
        return args.handler(ctx, args)
    except GuildError as error:
        sys.stderr.write("guild: {}\n".format(error.message))
        return error.exit_code
