from guild import names


def record_ctx(state_dir, session_id, pct):
    directory = state_dir / "ctx"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / names.safe_key(session_id)).write_text(str(pct))


def record_baseline_once(state_dir, session_id, pct):
    path = state_dir / "ctx-baseline" / names.safe_key(session_id)
    if pct == 0 or path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pct))


def read_ctx(state_dir, session_id):
    return read_pct(state_dir / "ctx" / names.safe_key(session_id))


def ctx_recorded_at(state_dir, session_id):
    return (state_dir / "ctx" / names.safe_key(session_id)).stat().st_mtime


def read_baseline(state_dir, session_id):
    return read_pct(state_dir / "ctx-baseline" / names.safe_key(session_id))


def latest_baseline(state_dir):
    directory = state_dir / "ctx-baseline"
    if not directory.is_dir():
        return None
    files = sorted(directory.iterdir(), key=lambda path: path.stat().st_mtime)
    if not files:
        return None
    return read_pct(files[-1])


def read_pct(path):
    if not path.is_file():
        return None
    try:
        return int(path.read_text().strip())
    except ValueError:
        return None


def record_compact_pct(state_dir, pct):
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "compaction-pct").write_text("{}\n".format(pct))


def latest_compact_pct(state_dir):
    path = state_dir / "compaction-pct"
    if not path.is_file():
        return None
    samples = [int(line) for line in path.read_text().split() if line.isdigit()]
    if not samples:
        return None
    return samples[-1]
