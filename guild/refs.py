import re

from guild.errors import GuildError

_PR_RE = re.compile(r"^([^/#]+/[^/#]+)#(\d+)$")
_TASK_RE = re.compile(r"^([^/]+)/(.+)$")
_ASK_REF_RE = re.compile(r"^(pr|task|card):(.+)$")
_CARD_KEY_RE = re.compile(r"^[^\s/]+$")
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


def parse_card_key(text):
    if not _CARD_KEY_RE.match(text):
        raise GuildError("invalid card ref '{}': expected a key without spaces or slashes".format(text), 1)
    return text


def parse_ask_ref(text):
    match = _ASK_REF_RE.match(text)
    if not match:
        raise GuildError(
            "invalid ask ref '{}': expected pr:owner/repo#number, task:quest/tid or card:KEY".format(text),
            1,
        )
    kind, rest = match.group(1), match.group(2)
    if kind == "pr":
        repo, number = parse_pr_ref(rest)
        return "pr:{}#{}".format(repo, number)
    if kind == "card":
        return "card:{}".format(parse_card_key(rest))
    quest, tid = parse_task_ref(rest)
    return "task:{}/{}".format(quest, tid)


def parse_until(text):
    match = _UNTIL_RE.match(text)
    if not match:
        raise GuildError("invalid --until '{}': expected pr:owner/repo#number:merged|closed".format(text), 1)
    return {"repo": match.group(1), "number": int(match.group(2)), "state": match.group(3)}
