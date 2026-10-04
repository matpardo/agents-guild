import subprocess

_GIT_IDENTITY = ["-c", "user.name=tester", "-c", "user.email=tester@example.com"]


def probe_result(exit_code, stdout, stderr, timed_out, error):
    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": timed_out,
        "error": error,
    }


def ok_result(stdout):
    return probe_result(0, stdout, "", False, None)


def failed_result(exit_code, stdout, stderr):
    return probe_result(exit_code, stdout, stderr, False, None)


def timeout_result():
    return probe_result(None, "", "", True, None)


def error_result(message):
    return probe_result(None, "", "", False, message)


class FakeProbe:
    def __init__(self, responder):
        self.responder = responder
        self.calls = []

    def __call__(self, argv, timeout_seconds):
        self.calls.append({"argv": list(argv), "timeout_seconds": timeout_seconds})
        return self.responder(argv)

    def argvs(self):
        return [call["argv"] for call in self.calls]


class FakeClock:
    def __init__(self, readings):
        self.readings = list(readings)
        self.last = readings[-1]

    def __call__(self):
        if self.readings:
            self.last = self.readings.pop(0)
        return self.last


def git(path, args):
    subprocess.run(["git"] + _GIT_IDENTITY + ["-C", str(path)] + args, check=True, capture_output=True)


def init_clone(path, repo):
    path.mkdir(parents=True, exist_ok=True)
    git(path, ["init", "-q"])
    git(path, ["remote", "add", "origin", "https://github.com/{}".format(repo)])
    git(path, ["commit", "-q", "--allow-empty", "-m", "initial"])


def add_worktree(clone, worktree_path, branch):
    git(clone, ["worktree", "add", "-q", "-b", branch, str(worktree_path)])


def write_bytes(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
