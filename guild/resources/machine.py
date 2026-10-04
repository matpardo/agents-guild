import re
import shutil

_MEMINFO_LINE_RE = re.compile(r"^(MemTotal|MemAvailable):\s+(\d+)\s+kB$", re.MULTILINE)
_KIBIBYTE = 1024
_SIDECAR_SUFFIXES = ("-wal", "-shm")


def read_memory(meminfo_path):
    try:
        text = meminfo_path.read_text()
    except OSError:
        return None, None
    values = {name: int(amount) * _KIBIBYTE for name, amount in _MEMINFO_LINE_RE.findall(text)}
    if "MemTotal" not in values or "MemAvailable" not in values:
        return None, None
    return values["MemTotal"], values["MemAvailable"]


def _file_bytes(path):
    try:
        return path.stat().st_size
    except OSError:
        return 0


def database_bytes(db_path):
    total = _file_bytes(db_path)
    for suffix in _SIDECAR_SUFFIXES:
        total += _file_bytes(db_path.parent / (db_path.name + suffix))
    return total


def _disk_totals(root_path):
    try:
        usage = shutil.disk_usage(str(root_path))
    except OSError:
        return None, None
    return usage.total, usage.used


def snapshot(root_path, meminfo_path, db_path):
    disk_total, disk_used = _disk_totals(root_path)
    mem_total, mem_available = read_memory(meminfo_path)
    return {
        "disk_total": disk_total,
        "disk_used": disk_used,
        "mem_total": mem_total,
        "mem_available": mem_available,
        "guild_db_bytes": database_bytes(db_path),
    }
