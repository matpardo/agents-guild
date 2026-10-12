import re

from guild import config
from guild.errors import GuildError

NOTICE_TEXT_MAX_LENGTH = 500
ASK_QUESTION_MAX_LENGTH = 300
ASK_CONTEXT_MAX_LENGTH = 2000
ANSWER_MAX_LENGTH = 1000
HANDOFF_FIELD_MAX_LENGTH = 4000
DISPATCH_PAUSE_REASON_MAX_LENGTH = 300

BROADCAST_REMINDER = (
    "note: this text is broadcast to every session and may be exported"
    " — never include names or identifiers of real people"
)

LOCAL_ONLY_REMINDER = (
    "guild is local and optional: never mention guild, ask #N, notice #N, party, raid or quest"
    " in PRs, comments, commits, sdd-docs or cards; cite a decision as \"decisión del dev\" with its date"
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_SECRET_PATTERNS = (
    r"\bghp_[A-Za-z0-9]+",
    r"\bgithub_pat_[A-Za-z0-9_]+",
    r"\bsk-[A-Za-z0-9]+",
    r"\bAKIA[A-Z0-9]+",
    r"\bxox[abp]-[A-Za-z0-9-]+",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
)
_SECRET_RE = re.compile("|".join(_SECRET_PATTERNS))

_INSTRUCTION_LIKE_PATTERNS = (
    r"\borden del dev\b",
    r"\bdev order\b",
    r"\bdecision del dev\b",
    r"\bignore previous\b",
    r"\bignora lo anterior\b",
    r"\bdisregard the above\b",
    r"\bnew instructions\b",
    r"\bsystem prompt\b",
    r"\brm -rf\b",
    r"\bcurl\s*\|\s*sh\b",
    r"\bgit push --force\b(?!-with-lease)",
)
_INSTRUCTION_LIKE_RE = re.compile("|".join(_INSTRUCTION_LIKE_PATTERNS), re.IGNORECASE)

INSTRUCTION_LIKE_FLAG = "[flagged: looks like an instruction or a command]"


def looks_instruction_like(value):
    return bool(_INSTRUCTION_LIKE_RE.search(value))


def _enforce_length(value, field_name, max_length):
    if len(value) > max_length:
        raise GuildError(
            "{} exceeds the maximum length of {} characters".format(field_name, max_length), 1
        )


def _enforce_no_email(value, field_name):
    if _EMAIL_RE.search(value):
        raise GuildError("{} must not contain an email address".format(field_name), 1)


def _enforce_no_secret(value, field_name):
    if _SECRET_RE.search(value):
        raise GuildError("{} must not contain a secret pattern".format(field_name), 1)


def _enforce_project_patterns(value, field_name, patterns):
    for pattern in patterns:
        if re.search(pattern, value):
            raise GuildError(
                "{} matches a pattern forbidden for this project".format(field_name), 1
            )


def validate_field(value, field_name, max_length, patterns):
    _enforce_length(value, field_name, max_length)
    _enforce_no_email(value, field_name)
    _enforce_no_secret(value, field_name)
    _enforce_project_patterns(value, field_name, patterns)


def project_patterns(projects_dir, project_name):
    if project_name is None:
        return []
    project_data = config.load_project(projects_dir, project_name)
    return project_data.get("pii_patterns") or []
