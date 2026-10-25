from guild import session_info

_SUBAGENT_TTL_SECONDS = 2 * 60 * 60
_PR_PREFIX = "pr-"
_SUBAGENT_PREFIX = "subagent-"


def _session_dir(state_dir, session_id):
    return state_dir / "background" / session_id


def mark(state_dir, session_id, key, label):
    directory = _session_dir(state_dir, session_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / key).write_text(label)


def clear(state_dir, session_id, key):
    (_session_dir(state_dir, session_id) / key).unlink(missing_ok=True)


def clear_subagents(state_dir, session_id):
    directory = _session_dir(state_dir, session_id)
    if not directory.is_dir():
        return
    for entry in directory.glob(_SUBAGENT_PREFIX + "*"):
        entry.unlink(missing_ok=True)


def pr_key(pid):
    return "{}{}".format(_PR_PREFIX, pid)


def subagent_key(agent_id):
    return "{}{}".format(_SUBAGENT_PREFIX, agent_id)


def _is_live(entry, now):
    if entry.name.startswith(_PR_PREFIX):
        pid = entry.name[len(_PR_PREFIX):]
        return pid.isdigit() and session_info.pid_alive(int(pid))
    return now.timestamp() - entry.stat().st_mtime < _SUBAGENT_TTL_SECONDS


def labels(state_dir, session_id, now):
    directory = _session_dir(state_dir, session_id)
    if not directory.is_dir():
        return []
    pr_labels = []
    subagents = 0
    for entry in sorted(directory.iterdir()):
        if not _is_live(entry, now):
            entry.unlink(missing_ok=True)
            continue
        if entry.name.startswith(_PR_PREFIX):
            pr_labels.append(entry.read_text())
            continue
        subagents += 1
    if subagents:
        pr_labels.append("{} subagents".format(subagents))
    return pr_labels
