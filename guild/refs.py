import re

from guild.errors import GuildError

_PR_RE = re.compile(r"^([^/#]+/[^/#]+)#(\d+)$")
_TASK_RE = re.compile(r"^([^/]+)/(.+)$")
_ASK_REF_RE = re.compile(r"^(pr|task):(.+)$")
_UNTIL_RE = re.compile(r"^pr:([^/#]+/[^/#]+)#(\d+):(merged|closed)$")


def parse_pr_ref(text):
    match = _PR_RE.match(text)
    if not match:
        raise GuildError("invalid PR ref '{}': expected owner/repo#number".format(text), 1)
    return match.group(1), int(match.group(2))


def parse_task_ref(text):
    match = _TASK_RE.match(text)
    if not match:
        raise GuildError("invalid task ref '{}': expected quest/tid".format(text), 1)
    return match.group(1), match.group(2)


def parse_ask_ref(text):
    match = _ASK_REF_RE.match(text)
    if not match:
        raise GuildError(
            "invalid ask ref '{}': expected pr:owner/repo#number or task:quest/tid".format(text),
            1,
        )
    kind, rest = match.group(1), match.group(2)
    if kind == "pr":
        repo, number = parse_pr_ref(rest)
        return "pr:{}#{}".format(repo, number)
    quest, tid = parse_task_ref(rest)
    return "task:{}/{}".format(quest, tid)


def parse_until(text):
    match = _UNTIL_RE.match(text)
    if not match:
        raise GuildError(
            "invalid --until '{}': expected pr:owner/repo#number:merged|closed".format(text), 1
        )
    return {"repo": match.group(1), "number": int(match.group(2)), "state": match.group(3)}

