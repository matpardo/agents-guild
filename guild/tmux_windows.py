import shutil
import subprocess

SESSION = "guild"


class Tmux:
    def installed(self):
        return shutil.which("tmux") is not None

    def run(self, args):
        completed = subprocess.run(["tmux", *args], capture_output=True, text=True)
        return completed.returncode, completed.stdout


def _ok(tmux, args):
    returncode, _ = tmux.run(args)
    return returncode == 0


def session_exists(tmux):
    return _ok(tmux, ["has-session", "-t", SESSION])


def window_names(tmux):
    returncode, output = tmux.run(["list-windows", "-t", SESSION, "-F", "#{window_name}"])
    if returncode != 0:
        return set()
    return {line for line in output.splitlines() if line}


def create_window(tmux, name, cwd, command, session_is_up):
    if session_is_up:
        args = ["new-window", "-t", SESSION + ":", "-n", name, "-c", cwd]
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


def set_title_options(tmux):
    _ok(tmux, ["set-option", "-t", SESSION, "set-titles", "on"])
    _ok(tmux, ["set-option", "-t", SESSION, "set-titles-string", "#W"])


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
