import os
import re
from pathlib import Path


def _xdg_dir(env_name, fallback_relative):
    value = os.environ.get(env_name)
    if value:
        return Path(value).expanduser() / "guild"
    return Path.home() / fallback_relative / "guild"


def data_dir():
    return _xdg_dir("XDG_DATA_HOME", ".local/share")


def config_dir():
    return _xdg_dir("XDG_CONFIG_HOME", ".config")


def state_dir():
    return _xdg_dir("XDG_STATE_HOME", ".local/state")


def db_path():
    return data_dir() / "guild.db"


def projects_config_dir():
    return config_dir() / "projects"


def handoffs_dir():
    return data_dir() / "handoffs"


def hint_shown_dir():
    return state_dir() / "hints"


def claude_sessions_dir():
    value = os.environ.get("GUILD_CLAUDE_SESSIONS_DIR")
    if value:
        return Path(value).expanduser()
    return Path.home() / ".claude" / "sessions"


def claude_projects_dir():
    value = os.environ.get("GUILD_CLAUDE_PROJECTS_DIR")
    if value:
        return Path(value).expanduser()
    return Path.home() / ".claude" / "projects"


def claude_scratch_dir():
    value = os.environ.get("GUILD_CLAUDE_SCRATCH_DIR")
    if value:
        return Path(value).expanduser()
    return Path("/tmp/claude-{}".format(os.getuid()))


def encode_cwd(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def ensure_private_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def systemd_user_dir():
    value = os.environ.get("XDG_CONFIG_HOME")
    if value:
        return Path(value).expanduser() / "systemd" / "user"
    return Path.home() / ".config" / "systemd" / "user"
