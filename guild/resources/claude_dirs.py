from guild import paths
from guild.resources import disk

CATEGORY_SCRATCH = "claude_scratch"
CATEGORY_TRANSCRIPTS = "claude_transcripts"
_SEPARATOR = "-"


def _owner_encodings(entries):
    return sorted(
        ((paths.encode_cwd(entry["path"]), entry) for entry in entries),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )


def _owner_of(name, encodings):
    for encoded, entry in encodings:
        if name == encoded or name.startswith(encoded + _SEPARATOR):
            return entry
    return None


def _owned_directories(base_dir, encodings):
    if not base_dir.is_dir():
        return {}
    owned = {}
    for child in sorted(base_dir.iterdir()):
        if not child.is_dir():
            continue
        owner = _owner_of(child.name, encodings)
        if owner is None:
            continue
        owned.setdefault(owner["path"], {"entry": owner, "directories": []})["directories"].append(child)
    return owned


def _combine(measurements):
    measured = [(size, state) for size, state in measurements if state != "missing"]
    if not measured:
        return None
    for _, state in measured:
        if state != "ok":
            return None, state
    return sum(size for size, _ in measured), "ok"


def _owner_row(category, owner, runner, deadline):
    measurements = [disk.du_bytes(str(directory), [], runner, deadline) for directory in owner["directories"]]
    combined = _combine(measurements)
    if combined is None:
        return None
    size, state = combined
    return (owner["entry"]["project"], [category, owner["entry"]["path"], size, state, "", ""])


def _category_rows(category, base_dir, encodings, runner, deadline):
    owned = _owned_directories(base_dir, encodings)
    rows = (_owner_row(category, owned[path], runner, deadline) for path in sorted(owned))
    return [row for row in rows if row is not None]


def sample(entries, scratch_dir, transcripts_dir, runner, deadline):
    encodings = _owner_encodings(entries)
    rows = _category_rows(CATEGORY_SCRATCH, scratch_dir, encodings, runner, deadline)
    rows.extend(_category_rows(CATEGORY_TRANSCRIPTS, transcripts_dir, encodings, runner, deadline))
    return rows
