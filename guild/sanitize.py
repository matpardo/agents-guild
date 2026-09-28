import re

_CSI_SEQUENCE_RE = re.compile(r"\x1b\[[0-9;:<=>?]*[ -/]*[@-~]")
_OSC_SEQUENCE_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_FE_SEQUENCE_RE = re.compile(r"\x1b[@-Z\\\]^_]")
_LONE_ESC_RE = re.compile(r"\x1b")
_C0_EXCEPT_NEWLINE_TAB_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_DEL_RE = re.compile(r"\x7f")
_C1_RE = re.compile(r"[\x80-\x9f]")


def strip_control_sequences(text):
    text = _CSI_SEQUENCE_RE.sub("", text)
    text = _OSC_SEQUENCE_RE.sub("", text)
    text = _FE_SEQUENCE_RE.sub("", text)
    text = _LONE_ESC_RE.sub("", text)
    text = _C0_EXCEPT_NEWLINE_TAB_RE.sub("", text)
    text = _DEL_RE.sub("", text)
    text = _C1_RE.sub("", text)
    return text


def collapse_to_single_line(text):
    return re.sub(r"[\n\t]", " ", text)


def sanitize_payload(value):
    if isinstance(value, str):
        return strip_control_sequences(value)
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_payload(item) for key, item in value.items()}
    return value
