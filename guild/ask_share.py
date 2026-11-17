import html as html_lib
import json
import re

from guild import sanitize

_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _clean(value):
    if not value:
        return None
    return sanitize.strip_control_sequences(value)


def _question(row):
    return _BOLD.sub(r"\1", sanitize.strip_control_sequences(row["question"]))


def _sections(row):
    options = json.loads(row["options"])
    sections = [("Context", _clean(row["context"]))]
    sections.append(("Options", [sanitize.strip_control_sequences(option) for option in options] or None))
    sections.append(("Recommendation", _clean(row["recommend"])))
    sections.append(("Answer", _clean(row["answer"])))
    return [(label, body) for label, body in sections if body is not None]


def text(row):
    blocks = ["**{}**".format(_question(row))]
    for label, body in _sections(row):
        if isinstance(body, list):
            body = "\n".join("- {}".format(option) for option in body)
        blocks.append("{}:\n{}".format(label, body))
    return "\n\n".join(blocks)


def _inline(value):
    return _BOLD.sub(lambda match: "<strong>{}</strong>".format(match.group(1)), html_lib.escape(value))


def _paragraphs(value):
    return "".join(
        "<p>{}</p>".format("<br>".join(_inline(line) for line in block.split("\n"))) for block in value.split("\n\n")
    )


def html(row):
    parts = ["<p><strong>{}</strong></p>".format(html_lib.escape(_question(row)))]
    for label, body in _sections(row):
        parts.append("<p><strong>{}:</strong></p>".format(label))
        if isinstance(body, list):
            parts.append("<ul>{}</ul>".format("".join("<li>{}</li>".format(_inline(option)) for option in body)))
            continue
        parts.append(_paragraphs(body))
    return "".join(parts)
