import re

_HUMAN_SIZE_RE = re.compile(r"^(\d+(?:\.\d+)?)(B|kB|MB|GB|TB)$")
_UNIT_BYTES = {"B": 1, "kB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}
_DU_LINE_RE = re.compile(r"^(\d+)\t")


def parse_human_size(text):
    if not text:
        return None
    tokens = text.split()
    if not tokens:
        return None
    match = _HUMAN_SIZE_RE.match(tokens[0])
    if match is None:
        return None
    amount, unit = match.groups()
    return int(round(float(amount) * _UNIT_BYTES[unit]))


def parse_du_output(text):
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    match = _DU_LINE_RE.match(lines[-1])
    if match is None:
        return None
    return int(match.group(1))
