import json
import subprocess


class GhCommandError(Exception):
    pass


def pr_view(cwd, repo, number, fields):
    result = subprocess.run(
        ["gh", "pr", "view", str(number), "--repo", repo, "--json", ",".join(fields)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GhCommandError(result.stderr.strip() or "gh pr view failed")
    return json.loads(result.stdout)


def pr_diff(cwd, repo, number):
    result = subprocess.run(
        [
            "gh", "pr", "view", str(number), "--repo", repo, "--json",
            "files,additions,deletions,createdAt",
        ],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GhCommandError(result.stderr.strip() or "gh pr view failed")
    data = json.loads(result.stdout)
    return {
        "paths": [entry["path"] for entry in data["files"]],
        "additions": data["additions"],
        "deletions": data["deletions"],
        "created_at": data["createdAt"],
    }


def pr_list_for_branch(cwd, branch, fields):
    result = subprocess.run(
        ["gh", "pr", "list", "--head", branch, "--state", "all", "--json", ",".join(fields)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GhCommandError(result.stderr.strip() or "gh pr list failed")
    return json.loads(result.stdout)


def pr_list_open(cwd, repo, fields):
    result = subprocess.run(
        ["gh", "pr", "list", "--repo", repo, "--state", "open", "--json", ",".join(fields)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GhCommandError(result.stderr.strip() or "gh pr list failed")
    return json.loads(result.stdout)


def branch_checks(cwd, repo, branch):
    result = subprocess.run(
        ["gh", "api", "repos/{}/commits/{}/check-runs".format(repo, branch)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GhCommandError(result.stderr.strip() or "gh api check-runs failed")
    return [
        {"name": run["name"], "conclusion": (run.get("conclusion") or "").upper()}
        for run in json.loads(result.stdout)["check_runs"]
    ]
