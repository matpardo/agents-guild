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


def pr_ready(cwd, repo, number):
    result = subprocess.run(
        ["gh", "pr", "ready", str(number), "--repo", repo],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GhCommandError(result.stderr.strip() or "gh pr ready failed")


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
        {
            "id": run.get("id"),
            "name": run["name"],
            "conclusion": (run.get("conclusion") or "").upper(),
            "annotations_count": (run.get("output") or {}).get("annotations_count") or 0,
        }
        for run in json.loads(result.stdout)["check_runs"]
    ]


def check_run_annotation_messages(cwd, repo, check_run_id):
    result = subprocess.run(
        ["gh", "api", "repos/{}/check-runs/{}/annotations".format(repo, check_run_id)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GhCommandError(result.stderr.strip() or "gh api annotations failed")
    return [annotation.get("message") or "" for annotation in json.loads(result.stdout)]


_UNRESOLVED_THREADS_QUERY = (
    "query($owner: String!, $name: String!, $number: Int!) {"
    " repository(owner: $owner, name: $name) {"
    " pullRequest(number: $number) {"
    " reviewThreads(first: 100) { nodes { isResolved } } } } }"
)


def unresolved_thread_count(cwd, repo, number):
    owner, name = repo.split("/", 1)
    result = subprocess.run(
        [
            "gh", "api", "graphql",
            "-f", "query={}".format(_UNRESOLVED_THREADS_QUERY),
            "-F", "owner={}".format(owner),
            "-F", "name={}".format(name),
            "-F", "number={}".format(number),
        ],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GhCommandError(result.stderr.strip() or "gh api graphql failed")
    nodes = json.loads(result.stdout)["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    return sum(1 for node in nodes if not node["isResolved"])
