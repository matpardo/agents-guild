import heapq
from collections import deque

_CLOSED_LIFECYCLES = ("merged", "closed")
_READY_LIFECYCLE = "ready"
_CONFLICTING = "CONFLICTING"
_CHANGES_REQUESTED = "CHANGES_REQUESTED"
_BEHIND = "BEHIND"
_HUMAN_AUTHOR = "human"
_DRAFT_LIFECYCLES = ("draft", "converging")
_READY_STATE = "ready"
CI_PENDING_STATE = "ready (CI pending)"
HUMAN_READY_STATES = (_READY_STATE, CI_PENDING_STATE)
NO_CHECKS_MISSING = "no checks on head"
_WAITING_STATE = "waiting"
_BLOCKED_STATE = "blocked"
_MERGE_ACTION = "merge"
_PROMOTE_ACTION = "promote"
REVIEW_ACTION = "review: human, then merge"
MERGEABLE_ACTIONS = (_MERGE_ACTION, REVIEW_ACTION)
_ASK_LABEL = "needs-ask-answer"
_REVIEW_LABEL = "needs-human-pr-review"
_FIXES_MAIN_LABEL = "fixes-main"
_FIXES_FLAKY_LABEL = "fixes-flaky"
_BLOCKED_EXTERNAL_LABEL = "blocked-external"


def _is_open(pr):
    return pr["lifecycle"] not in _CLOSED_LIFECYCLES


def review_reasons(mergeable, review_decision, unresolved_threads, merge_state):
    reasons = []
    if mergeable == _CONFLICTING:
        reasons.append("merge conflict")
    if review_decision == _CHANGES_REQUESTED:
        reasons.append("changes requested")
    if unresolved_threads:
        reasons.append("{} unresolved thread{}".format(unresolved_threads, "" if unresolved_threads == 1 else "s"))
    if merge_state == _BEHIND:
        reasons.append("behind base")
    return reasons


def fix_reasons(pr):
    reasons = []
    if pr["checks_failing"] and not pr["checks_billing"]:
        reasons.append("checks failing ({})".format(pr["checks_failing"]))
    reasons.extend(review_reasons(pr["mergeable"], pr["review_decision"], pr["unresolved_threads"], pr["merge_state"]))
    return reasons


def _ask_text(text, pr):
    if pr["ask_id"] is None:
        return text
    return "{} (ask #{})".format(text, pr["ask_id"])


def _blocked_reasons(pr):
    reasons = []
    if pr["blocked_external"] is not None:
        reasons.append("manual block: {}".format(pr["blocked_external"]))
    if pr["needs_ask_answer"]:
        reasons.append(_ask_text("needs ask answer", pr))
    reasons.extend(fix_reasons(pr))
    for tid in pr["unmet_deps"]:
        reasons.append("waits on task {}".format(tid))
    return reasons


def _wait_reasons(pr):
    if pr["checks_pending"] > 0:
        return ["checks pending ({})".format(pr["checks_pending"])]
    return []


def _is_draft(pr):
    return pr["lifecycle"] in _DRAFT_LIFECYCLES


def _labels(pr):
    labels = []
    if _is_draft(pr):
        labels.append(pr["lifecycle"])
    if pr["fixes_main"]:
        labels.append(_FIXES_MAIN_LABEL)
    if pr["fixes_flaky"]:
        labels.append(_FIXES_FLAKY_LABEL)
    if pr["needs_ask_answer"]:
        labels.append(_ask_text(_ASK_LABEL, pr))
    if pr["needs_human_pr_review"]:
        labels.append(_REVIEW_LABEL)
    if pr["blocked_external"] is not None:
        labels.append(_BLOCKED_EXTERNAL_LABEL)
    if pr["checks_billing"] == 1:
        labels.append("checks blocked by billing ({})".format(pr["checks_failing"]))
    return labels


def unblocks_everyone(pr):
    return bool(pr["fixes_main"] or pr["fixes_flaky"])


def urgency_clause(pr):
    if pr["fixes_main"] and pr["fixes_flaky"]:
        return "fixes a broken main and flaky tests"
    if pr["fixes_main"]:
        return "fixes a broken main"
    return "fixes flaky tests"


def _entry(pr):
    task = pr["card"]
    if pr["quest"] is not None:
        task = "{}/{}".format(pr["quest"], pr["tid"])
    return {
        "ref": pr["ref"],
        "repo": pr["repo"],
        "number": pr["number"],
        "party": pr["party"],
        "task": task,
        "lifecycle": pr["lifecycle"],
        "branch": pr["branch"],
        "checks_failing": pr["checks_failing"],
        "checks_passing": pr["checks_passing"],
        "checks_pending": pr["checks_pending"],
        "checks_billing": pr["checks_billing"],
        "ci_label": pr["ci_label"],
        "labels": _labels(pr),
        "unseen_comments": pr["unseen_comments"],
    }


def find_path(pairs, start, goal):
    successors = {}
    for first, second in pairs:
        successors.setdefault(first, []).append(second)
    parents = {start: None}
    pending = deque([start])
    while pending:
        node = pending.popleft()
        if node == goal:
            return _walk_back(parents, goal)
        for following in successors.get(node, []):
            if following not in parents:
                parents[following] = node
                pending.append(following)
    return None


def _walk_back(parents, goal):
    path = []
    node = goal
    while node is not None:
        path.append(node)
        node = parents[node]
    path.reverse()
    return path


def dependency_pairs(prs):
    by_task = {}
    for pr in prs:
        if pr["task_key"] is not None:
            by_task.setdefault(pr["task_key"], []).append(pr["ref"])
    pairs = []
    for pr in prs:
        for dep_key in pr["dep_keys"]:
            for dep_ref in by_task.get(dep_key, []):
                if dep_ref != pr["ref"]:
                    pairs.append((dep_ref, pr["ref"]))
    return pairs


def _task_edges(open_prs):
    by_ref = {pr["ref"]: pr for pr in open_prs}
    edges = []
    for first, second in dependency_pairs(open_prs):
        edges.append(
            {
                "first": first,
                "second": second,
                "before": "before {} (task {} depends on {})".format(
                    second, by_ref[second]["tid"], by_ref[first]["tid"]
                ),
                "after": "after {} (needs task {})".format(first, by_ref[first]["tid"]),
            }
        )
    return edges


def stack_pairs(prs):
    by_branch = {(pr["repo"], pr["branch"]): pr["ref"] for pr in prs if pr["branch"] is not None}
    pairs = []
    for pr in prs:
        parent = by_branch.get((pr["repo"], pr["base_branch"]))
        if parent is not None and parent != pr["ref"]:
            pairs.append((parent, pr["ref"]))
    return pairs


def _stack_edges(open_prs):
    return [
        {
            "first": first,
            "second": second,
            "before": "before {} (it is stacked on this)".format(second),
            "after": "after {} (stacked on it)".format(first),
        }
        for first, second in stack_pairs(open_prs)
    ]


def _pin_edges(open_refs, pins):
    edges = []
    for pin in pins:
        if pin["first"] not in open_refs or pin["second"] not in open_refs:
            continue
        author = pin["author"] or _HUMAN_AUTHOR
        edges.append(
            {
                "first": pin["first"],
                "second": pin["second"],
                "before": "pinned before {} by {}".format(pin["second"], author),
                "after": "pinned after {} by {}".format(pin["first"], author),
            }
        )
    return edges


def _shared_globs(first, second):
    if first["repo"] != second["repo"]:
        return []
    return sorted(set(first["globs"]) & set(second["globs"]))


def _successors(edges):
    successors = {}
    for edge in edges:
        successors.setdefault(edge["first"], set()).add(edge["second"])
    return successors


def _predecessors(edges):
    predecessors = {}
    for edge in edges:
        predecessors.setdefault(edge["second"], set()).add(edge["first"])
    return predecessors


def _dependents(successors, ref):
    seen = set()
    pending = list(successors.get(ref, ()))
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        pending.extend(successors.get(node, ()))
    seen.discard(ref)
    return seen


def _glob_sharers(pr, open_prs):
    return {other["ref"] for other in open_prs if other["ref"] != pr["ref"] and _shared_globs(pr, other)}


def _unblock_counts(open_prs, edges):
    successors = _successors(edges)
    return {pr["ref"]: len(_dependents(successors, pr["ref"]) | _glob_sharers(pr, open_prs)) for pr in open_prs}


def _topological_order(open_prs, edges, unblocks):
    tie_keys = {pr["ref"]: (pr["number"], pr["repo"]) for pr in open_prs}
    sort_keys = {
        pr["ref"]: (0 if unblocks_everyone(pr) else 1, -unblocks[pr["ref"]]) + tie_keys[pr["ref"]] for pr in open_prs
    }
    blockers = {pr["ref"]: 0 for pr in open_prs}
    successors = _successors(edges)
    for first in successors:
        for second in successors[first]:
            blockers[second] += 1
    heap = [(sort_keys[ref], ref) for ref, count in blockers.items() if count == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        _, ref = heapq.heappop(heap)
        order.append(ref)
        for following in successors.get(ref, ()):
            blockers[following] -= 1
            if blockers[following] == 0:
                heapq.heappush(heap, (sort_keys[following], following))
    stuck = sorted((ref for ref in blockers if ref not in order), key=lambda ref: tie_keys[ref])
    return order, stuck


def _base_reason(pr):
    if pr["checks_passing"] == 0:
        return "ready, no checks"
    return "ready, checks ✓{}".format(pr["checks_passing"])


def _why(pr, state, position, edges):
    clauses = []
    if unblocks_everyone(pr):
        clauses.append(urgency_clause(pr))
    if state == _READY_STATE:
        clauses.append(_base_reason(pr))
    before = [edge for edge in edges if edge["first"] == pr["ref"]]
    after = [edge for edge in edges if edge["second"] == pr["ref"]]
    before.sort(key=lambda edge: position[edge["second"]])
    after.sort(key=lambda edge: position[edge["first"]])
    clauses.extend(edge["before"] for edge in before)
    clauses.extend(edge["after"] for edge in after)
    return "; ".join(clauses)


def _state(reasons, waits):
    if reasons:
        return _BLOCKED_STATE
    if waits:
        return _WAITING_STATE
    return _READY_STATE


def _action(pr, state, reasons, waits, external):
    if external is not None and external[0] == pr["ref"]:
        return "manual block: {}".format(external[1])
    if external is not None:
        return "waits on manually blocked {}: {}".format(*external)
    if state == _BLOCKED_STATE:
        return "fix: {} \u2192 {}".format("; ".join(reasons), pr["party"])
    if state == _WAITING_STATE:
        return "wait: {}".format("; ".join(waits))
    if _is_draft(pr):
        return "{}: gh pr ready \u2192 {}".format(_PROMOTE_ACTION, pr["party"])
    if pr["needs_human_pr_review"]:
        return REVIEW_ACTION
    return _MERGE_ACTION


def _no_checks(pr):
    return pr["checks_failing"] == 0 and pr["checks_passing"] == 0 and pr["checks_pending"] == 0


def _ci_pending(pr, billing):
    if pr["checks_billing"] == 1:
        return True
    return _no_checks(pr) and (billing or pr["ci_label"] == 0)


def _human_missing(pr, billing):
    missing = []
    comments = pr["comments_after_head"]
    if comments:
        missing.append("{} comment{} after head".format(comments, "" if comments == 1 else "s"))
    if _no_checks(pr) and not _is_draft(pr) and not _ci_pending(pr, billing):
        missing.append(NO_CHECKS_MISSING)
    if pr["trace_valid"] == 0:
        missing.append("review trace invalid: {}".format(pr["trace_reason"]))
    if pr["trace_valid"] is None and pr["trace_reason"]:
        missing.append("review trace not validated: {}".format(pr["trace_reason"]))
    return missing


def _human_state(pr, state, missing, billing):
    if state == _BLOCKED_STATE or pr["comments_after_head"] or pr["trace_valid"] == 0:
        return _BLOCKED_STATE
    if state == _WAITING_STATE or missing or _is_draft(pr):
        return _WAITING_STATE
    if _ci_pending(pr, billing):
        return CI_PENDING_STATE
    return _READY_STATE


def _queue_entry(pr, unblocks, reasons, waits, why, external, billing):
    state = _state(reasons, waits)
    missing = _human_missing(pr, billing)
    return dict(
        _entry(pr),
        human_state=_human_state(pr, state, missing, billing),
        human_missing=missing,
        unblocks=unblocks,
        state=state,
        reasons=reasons if state == _BLOCKED_STATE else waits,
        blockers=reasons,
        waits=waits,
        why=why,
        action=_action(pr, state, reasons, waits, external),
        external=None if external is None else external[1],
        blocked_external=pr["blocked_external"],
        next_action=False,
    )


def _ordered_entries(by_ref, order, edges, unblocks, billing_repos):
    position = {ref: index for index, ref in enumerate(order)}
    ordered_edges = [edge for edge in edges if edge["first"] in position and edge["second"] in position]
    predecessors = _predecessors(ordered_edges)
    blocked_refs = set()
    pending_refs = set()
    unready_refs = set()
    external_reasons = {}
    entries = []
    for ref in order:
        pr = by_ref[ref]
        before = sorted(predecessors.get(ref, ()))
        reasons = _blocked_reasons(pr)
        reasons.extend("waits on {}".format(first) for first in before if first in blocked_refs)
        waits = _wait_reasons(pr)
        waits.extend("waits on {}".format(first) for first in before if first in pending_refs)
        state = _state(reasons, waits)
        external = _own_external(pr)
        if external is None:
            external = next((external_reasons[first] for first in before if first in external_reasons), None)
        if external is not None:
            external_reasons[ref] = external
        if state == _BLOCKED_STATE:
            blocked_refs.add(ref)
        if state == _WAITING_STATE or (state == _READY_STATE and _is_draft(pr)):
            pending_refs.add(ref)
        entry = _queue_entry(
            pr,
            unblocks[ref],
            reasons,
            waits,
            _why(pr, state, position, ordered_edges),
            external,
            pr["repo"] in billing_repos,
        )
        _hold_behind_unready(entry, before, unready_refs, reasons + waits)
        if entry["human_state"] not in HUMAN_READY_STATES:
            unready_refs.add(ref)
        entries.append(entry)
    return entries


def _hold_behind_unready(entry, before, unready_refs, stated):
    held = ["waits on {}".format(first) for first in before if first in unready_refs]
    held = [line for line in held if line not in stated]
    if not held:
        return
    entry["human_missing"] = entry["human_missing"] + held
    if entry["human_state"] in HUMAN_READY_STATES:
        entry["human_state"] = _WAITING_STATE


def _own_external(pr):
    if pr["blocked_external"] is None:
        return None
    return (pr["ref"], pr["blocked_external"])


def _stuck_entries(by_ref, stuck, unblocks, billing_repos):
    cycle = "ordering cycle between pins and task dependencies: {}".format(", ".join(stuck))
    return [
        _queue_entry(
            by_ref[ref],
            unblocks[ref],
            _blocked_reasons(by_ref[ref]) + [cycle],
            [],
            "",
            _own_external(by_ref[ref]),
            by_ref[ref]["repo"] in billing_repos,
        )
        for ref in stuck
    ]


def _flag_next_action(entries):
    for index, entry in enumerate(entries):
        if entry["state"] != _BLOCKED_STATE or entry["external"] is not None:
            continue
        if any(later["action"] == _MERGE_ACTION for later in entries[index + 1 :]):
            entry["next_action"] = True
        return


def _main_entries(main_status):
    return sorted((dict(row) for row in main_status), key=lambda row: (row["repo"], row["source"]))


def compute(prs, pins, main_status):
    open_prs = [pr for pr in prs if _is_open(pr)]
    open_refs = {pr["ref"] for pr in open_prs}
    edges = _task_edges(open_prs) + _stack_edges(open_prs) + _pin_edges(open_refs, pins)
    unblocks = _unblock_counts(open_prs, edges)
    order, stuck = _topological_order(open_prs, edges, unblocks)
    by_ref = {pr["ref"]: pr for pr in open_prs}
    billing_repos = {row["repo"] for row in main_status if row["external"] == "billing"}
    entries = _ordered_entries(by_ref, order, edges, unblocks, billing_repos) + _stuck_entries(
        by_ref, stuck, unblocks, billing_repos
    )
    _flag_next_action(entries)
    return {"main": _main_entries(main_status), "queue": entries}


def ready_for_person(entries, main):
    red_repos = {row["repo"] for row in main if row["external"] is None}
    return [
        entry
        for entry in entries
        if entry["lifecycle"] == _READY_LIFECYCLE
        and entry["human_state"] in HUMAN_READY_STATES
        and entry["external"] is None
        and entry["action"] in MERGEABLE_ACTIONS
        and entry["repo"] not in red_repos
    ]
