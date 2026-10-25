import os
import shutil
import subprocess

SESSION = "guild"
HYPERLINK_FEATURE_SLOT = "terminal-features[10]"
OPEN_LINK_ON_CTRL_CLICK = [
    "bind-key",
    "-n",
    "C-MouseDown1Pane",
    "if-shell",
    "-F",
    "#{mouse_hyperlink}",
    "run-shell -b 'xdg-open -- #{q:mouse_hyperlink}'",
    "send-keys -M",
]
X11_CLIPBOARD_COMMANDS = (
    ("xclip", "xclip -selection clipboard -in"),
    ("xsel", "xsel --clipboard --input"),
)


class Tmux:
    def installed(self):
        return shutil.which("tmux") is not None

    def run(self, args):
        completed = subprocess.run(["tmux", *args], capture_output=True, text=True)
        return completed.returncode, completed.stdout


def _ok(tmux, args):
    returncode, _ = tmux.run(args)
    return returncode == 0


def clipboard_command():
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        return "wl-copy"
    if not os.environ.get("DISPLAY"):
        return None
    for tool, command in X11_CLIPBOARD_COMMANDS:
        if shutil.which(tool):
            return command
    return None


def session_exists(tmux):
    return _ok(tmux, ["has-session", "-t", SESSION])


def window_names(tmux):
    returncode, output = tmux.run(["list-windows", "-t", SESSION, "-F", "#{window_name}"])
    if returncode != 0:
        return set()
    return {line for line in output.splitlines() if line}


def create_window(tmux, name, cwd, command, session_is_up):
    if session_is_up:
        args = ["new-window", "-t", SESSION + ":", "-n", name, "-c", cwd, "-d"]
    else:
        args = ["new-session", "-d", "-s", SESSION, "-n", name, "-c", cwd]
    returncode, output = tmux.run([*args, "-P", "-F", "#{window_id}", command])
    if returncode != 0:
        return None
    return output.strip()


def pin_window_name(tmux, window_id):
    return _ok(tmux, ["set-option", "-w", "-t", window_id, "automatic-rename", "off"]) and _ok(
        tmux, ["set-option", "-w", "-t", window_id, "allow-rename", "off"]
    )


def set_session_options(tmux):
    _ok(tmux, ["set-option", "-t", SESSION, "set-titles", "on"])
    _ok(tmux, ["set-option", "-t", SESSION, "set-titles-string", "#W"])
    _ok(tmux, ["set-option", "-t", SESSION, "mouse", "on"])
    _ok(tmux, ["set-option", "-s", "set-clipboard", "on"])
    copy_command = clipboard_command()
    if copy_command:
        _ok(tmux, ["set-option", "-s", "copy-command", copy_command])
    _ok(tmux, ["set-option", "-s", HYPERLINK_FEATURE_SLOT, "*:hyperlinks"])
    _ok(tmux, OPEN_LINK_ON_CTRL_CLICK)


def recorded_window(conn, party, generation):
    row = conn.execute(
        "SELECT window_id FROM leader_windows WHERE party = ? AND generation = ?", (party, generation)
    ).fetchone()
    if row is None:
        return None
    return row["window_id"]


def window_id_of_pane(tmux, pane):
    returncode, output = tmux.run(["display-message", "-p", "-t", pane, "#{window_id}"])
    if returncode != 0:
        return None
    return output.strip() or None


def window_in_session(tmux, window_id):
    returncode, output = tmux.run(["list-windows", "-t", SESSION, "-F", "#{window_id}"])
    if returncode != 0:
        return False
    return window_id in output.splitlines()


def kill_pane(tmux, pane):
    return _ok(tmux, ["kill-pane", "-t", pane])


def send_text(tmux, window_id, text):
    return _ok(tmux, ["send-keys", "-t", window_id, "-l", text]) and _ok(tmux, ["send-keys", "-t", window_id, "Enter"])
