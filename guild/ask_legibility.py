import re
import textwrap

from guild import sanitize

QUESTION_JARGON_LIMIT = 2
CONTEXT_JARGON_LIMIT = 6

TEMPLATE = (
    "write for someone who does not know the repo: what is decided, one --option per choice with its effect, "
    "and your --recommend with the reason"
)

_JARGON = re.compile(
    r"\S+\.(?:py|js|md|json|toml|sh)\b"
    r"|\w+(?:/\w+){2,}"
    r"|#\d+"
    r"|\bT\d{2,}\b"
    r"|\b[A-Z][A-Z0-9]+-\d+\b"
    r"|\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{7,40}\b"
    r"|`[^`]+`"
    r"|\b[a-z0-9]+(?:_[a-z0-9]+)+\b"
)
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def jargon_count(text):
    return len(_JARGON.findall(text))


def warning_lines(question, context_text):
    lines = []
    question_count = jargon_count(question)
    if question_count > QUESTION_JARGON_LIMIT:
        lines.append("warning: question carries {} ids or paths".format(question_count))
    context_count = jargon_count(context_text)
    if context_count > CONTEXT_JARGON_LIMIT:
        lines.append("warning: context carries {} ids or paths".format(context_count))
    if lines:
        lines.append("rewrite: {}".format(TEMPLATE))
    return lines


def ask_text_lines(text, indent, width, bold):
    lines = []
    for raw in sanitize.strip_control_sequences(text).split("\n"):
        if not raw.strip():
            lines.append("")
            continue
        lines.extend(
            textwrap.wrap(raw, width=width, initial_indent=indent, subsequent_indent=indent, break_on_hyphens=False)
        )
    if bold is None:
        return lines
    return [_BOLD.sub(lambda match: bold(match.group(1)), line) for line in lines]
