import heapq
from collections import deque

_CLOSED_LIFECYCLES = ("merged", "closed")
_READY_LIFECYCLE = "ready"
_CONFLICTING = "CONFLICTING"
_HUMAN_AUTHOR = "human"


def _is_open(pr):
    return pr["lifecycle"] not in _CLOSED_LIFECYCLES


def _blocked_reasons(pr):
    reasons = []
    if pr["lifecycle"] != _READY_LIFECYCLE:
        reasons.append(pr["lifecycle"])
    if pr["checks_failing"] > 0:
        reasons.append("checks failing ({})".format(pr["checks_failing"]))
    if pr["mergeable"] == _CONFLICTING:
        reasons.append("merge conflict")
    for tid in pr["unmet_deps"]:
        reasons.append("waits on task {}".format(tid))
    return reasons


def _entry(pr):
    task = None
    if pr["quest"] is not None:
        task = "{}/{}".format(pr["quest"], pr["tid"])
    return {
        "ref": pr["ref"],
        "repo": pr["repo"],
        "number": pr["number"],
        "party": pr["party"],
        "task": task,
        "lifecycle": pr["lifecycle"],
        "checks_failing": pr["checks_failing"],
        "checks_passing": pr["checks_passing"],
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


def _task_edges(eligible):
    by_ref = {pr["ref"]: pr for pr in eligible}
    edges = []
    for first, second in dependency_pairs(eligible):
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


def _pin_edges(eligible_refs, pins):
    edges = []
    for pin in pins:
        if pin["first"] not in eligible_refs or pin["second"] not in eligible_refs:
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


def _diff_size(pr):
    return pr["additions"] + pr["deletions"]


def _overlap_key(pr):
    return (_diff_size(pr), pr["created_at"], pr["number"])


def _overlap_reason(first, second):
    if _diff_size(first) != _diff_size(second):
        return "smaller diff"
    if first["created_at"] != second["created_at"]:
        return "created earlier"
    return "lower number"


def _shared_globs(first, second):
    if first["repo"] != second["repo"]:
        return []
    return sorted(set(first["globs"]) & set(second["globs"]))


def _oriented_overlaps(eligible):
    oriented = []
    for index, left in enumerate(eligible):
        for right in eligible[index + 1:]:
            globs = _shared_globs(left, right)
            if not globs:
                continue
            first, second = sorted((left, right), key=_overlap_key)
            oriented.append((first, second, globs))
    oriented.sort(key=lambda item: (_overlap_key(item[0]), _overlap_key(item[1])))
    return oriented


def _overlap_edges(eligible, hard_pairs):
    pairs = list(hard_pairs)
    edges = []
    for first, second, globs in _oriented_overlaps(eligible):
        if find_path(pairs, first["ref"], second["ref"]) or find_path(pairs, second["ref"], first["ref"]):
            continue
        pairs.append((first["ref"], second["ref"]))
        shared = ", ".join(globs)
        edges.append(
            {
                "first": first["ref"],
                "second": second["ref"],
                "before": "before {} (shares {}, {})".format(
                    second["ref"], shared, _overlap_reason(first, second)
                ),
                "after": "after {} (shares {})".format(first["ref"], shared),
            }
        )
    return edges


def _topological_order(eligible, edges):
    sort_keys = {pr["ref"]: (pr["number"], pr["repo"]) for pr in eligible}
    blockers = {pr["ref"]: 0 for pr in eligible}
    successors = {pr["ref"]: set() for pr in eligible}
    for first, second in {(edge["first"], edge["second"]) for edge in edges}:
        successors[first].add(second)
        blockers[second] += 1
    heap = [(sort_keys[ref], ref) for ref, count in blockers.items() if count == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        _, ref = heapq.heappop(heap)
        order.append(ref)
        for following in successors[ref]:
            blockers[following] -= 1
            if blockers[following] == 0:
                heapq.heappush(heap, (sort_keys[following], following))
    stuck = sorted((ref for ref in blockers if ref not in order), key=lambda ref: sort_keys[ref])
    return order, stuck


def _base_reason(pr):
    if pr["checks_passing"] == 0:
        return "ready, no checks"
    return "ready, checks ✓{}".format(pr["checks_passing"])


def _reason(pr, position, edges):
    clauses = [_base_reason(pr)]
    before = [edge for edge in edges if edge["first"] == pr["ref"]]
    after = [edge for edge in edges if edge["second"] == pr["ref"]]
    before.sort(key=lambda edge: position[edge["second"]])
    after.sort(key=lambda edge: position[edge["first"]])
    clauses.extend(edge["before"] for edge in before)
    clauses.extend(edge["after"] for edge in after)
    return "; ".join(clauses)


def compute(prs, pins):
    open_prs = [pr for pr in prs if _is_open(pr)]
    blocked = []
    eligible = []
    for pr in open_prs:
        reasons = _blocked_reasons(pr)
        if reasons:
            blocked.append(dict(_entry(pr), reasons=reasons))
            continue
        eligible.append(pr)
    eligible_refs = {pr["ref"] for pr in eligible}
    hard_edges = _task_edges(eligible) + _pin_edges(eligible_refs, pins)
    hard_pairs = [(edge["first"], edge["second"]) for edge in hard_edges]
    edges = hard_edges + _overlap_edges(eligible, hard_pairs)
    order, stuck = _topological_order(eligible, edges)
    by_ref = {pr["ref"]: pr for pr in eligible}
    for ref in stuck:
        reason = "ordering cycle between pins and task dependencies: {}".format(", ".join(stuck))
        blocked.append(dict(_entry(by_ref[ref]), reasons=[reason]))
    position = {ref: index for index, ref in enumerate(order)}
    edges = [edge for edge in edges if edge["first"] in position and edge["second"] in position]
    queue = [dict(_entry(by_ref[ref]), reason=_reason(by_ref[ref], position, edges)) for ref in order]
    blocked.sort(key=lambda entry: (entry["number"], entry["repo"]))
    return {"queue": queue, "blocked": blocked}
