import re
import subprocess
from pathlib import Path

_TID_TOKEN_RE = re.compile(r"T\d+\w*")


class GitSddError(Exception):
    pass


def _captured_text(match):
    if match.re.groups >= 1:
        return match.group(1)
    return match.group(0)


def _order_index(lines, order_list_re):
    order_index = {}
    counter = 0
    for line in lines:
        match = order_list_re.match(line.strip())
        if match is None:
            continue
        for tid in _TID_TOKEN_RE.findall(line):
            if tid in order_index:
                continue
            order_index[tid] = counter
            counter += 1
    return order_index


def _find_deps(body, deps_line_re):
    for line in body:
        match = deps_line_re.match(line.strip())
        if match is None:
            continue
        return _dedupe(_TID_TOKEN_RE.findall(_captured_text(match)))
    return []


def _dedupe(tids):
    seen = set()
    result = []
    for tid in tids:
        if tid in seen:
            continue
        seen.add(tid)
        result.append(tid)
    return result


def _find_status(body, status_line_re):
    for line in body:
        match = status_line_re.match(line.strip())
        if match is None:
            continue
        return "done" if "[x]" in _captured_text(match) else "pending"
    return "pending"


def _find_key_ref(heading_line, key_ref_re):
    match = key_ref_re.search(heading_line)
    if match is None:
        return None
    return _captured_text(match)


def _find_key_in_body(body, key_line_re, key_ref_re):
    for line in body:
        match = key_line_re.match(line.strip())
        if match is None:
            continue
        return _find_key_ref(_captured_text(match), key_ref_re)
    return None


def _task_key(heading_line, body, key_ref_re, key_line_re):
    heading_key = _find_key_ref(heading_line, key_ref_re)
    if heading_key is not None or key_line_re is None:
        return heading_key
    return _find_key_in_body(body, key_line_re, key_ref_re)


def parse_tasks_text(text, patterns):
    task_heading_re = re.compile(patterns["task_heading"])
    key_ref_re = re.compile(patterns["key_ref"])
    deps_line_re = re.compile(patterns["deps_line"])
    status_line_re = re.compile(patterns["status_line"])
    order_list_pattern = patterns.get("order_list")
    order_list_re = re.compile(order_list_pattern) if order_list_pattern else None
    key_line_pattern = patterns.get("key_line")
    key_line_re = re.compile(key_line_pattern) if key_line_pattern else None

    lines = text.splitlines()
    headings = []
    for index, line in enumerate(lines):
        match = task_heading_re.match(line.strip())
        if match is None:
            continue
        headings.append((index, match.group(1), match.group(2).strip()))

    if not headings:
        return None

    order_index = _order_index(lines, order_list_re) if order_list_re else {}

    tasks = []
    for position, (index, tid, title) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        body = lines[index + 1 : end]
        tasks.append(
            {
                "tid": tid,
                "title": title,
                "jira_key": _task_key(lines[index], body, key_ref_re, key_line_re),
                "deps": _find_deps(body, deps_line_re),
                "order_idx": order_index.get(tid),
                "sdd_status": _find_status(body, status_line_re),
            }
        )
    return tasks


def parse_tasks_file(path, patterns):
    text = Path(path).read_text()
    return parse_tasks_text(text, patterns)


def _frontmatter_fields(text):
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return {}
    end = None
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            end = index
            break
    if end is None:
        return {}
    fields = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if not sep:
            continue
        fields[key.strip()] = value.strip()
    return fields


def parse_epic_key(text, field):
    return _frontmatter_fields(text).get(field) or None


def parse_epic_status(text, field):
    return _frontmatter_fields(text).get(field) or None


def discover_epic_files(root, epics_dir):
    base = Path(root).expanduser() / epics_dir
    if not base.is_dir():
        return []
    files = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        tasks_file = entry / "tasks.md"
        if tasks_file.is_file():
            files.append((entry.name, tasks_file))
    return files


def _run_git(repo, args):
    result = subprocess.run(
        ["git", "-C", str(Path(repo).expanduser())] + args, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise GitSddError(result.stderr.strip() or "git {} failed".format(" ".join(args)))
    return result.stdout


def git_fetch(repo):
    _run_git(repo, ["fetch", "--quiet", "origin"])


def _epic_from_tasks_path(path, epics_dir):
    prefix = epics_dir.rstrip("/") + "/"
    if not path.startswith(prefix) or not path.endswith("/tasks.md"):
        return None
    middle = path[len(prefix) : -len("/tasks.md")]
    if not middle or "/" in middle:
        return None
    return middle


def git_tasks_files(repo, ref, epics_dir):
    output = _run_git(repo, ["ls-tree", "-r", "--name-only", ref, "--", epics_dir])
    files = []
    for line in output.splitlines():
        epic = _epic_from_tasks_path(line, epics_dir)
        if epic is None:
            continue
        files.append((epic, line))
    return sorted(files)


def git_show(repo, ref, path):
    return _run_git(repo, ["show", "{}:{}".format(ref, path)])
