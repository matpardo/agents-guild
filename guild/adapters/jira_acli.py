import json
import re
import subprocess

_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
_FIELDS = "key,status,issuetype"
_CHUNK_SIZE = 50


class JiraAcliError(Exception):
    pass


def _is_valid_key(key):
    return _KEY_RE.match(key) is not None


def _parse_item(item):
    fields = item["fields"]
    status = fields["status"]
    return {
        "key": item["key"],
        "status": status["name"],
        "status_category": status["statusCategory"]["key"],
        "issue_type": fields["issuetype"]["name"],
    }


def _search(jql):
    try:
        result = subprocess.run(
            ["acli", "jira", "workitem", "search", "--jql", jql, "--fields", _FIELDS, "--json", "--paginate"],
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise JiraAcliError("acli could not run: {}".format(error))
    if result.returncode != 0:
        raise JiraAcliError(result.stderr.strip() or "acli jira workitem search failed")
    try:
        items = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise JiraAcliError("unparseable acli output: {}".format(error))
    return [_parse_item(item) for item in items]


def children_of(epic_key):
    if not _is_valid_key(epic_key):
        return [], [epic_key]
    return _search("parent = {}".format(epic_key)), []


def cards_by_key(keys):
    valid_keys = [key for key in keys if _is_valid_key(key)]
    invalid_keys = [key for key in keys if not _is_valid_key(key)]
    cards = []
    for start in range(0, len(valid_keys), _CHUNK_SIZE):
        chunk = valid_keys[start : start + _CHUNK_SIZE]
        cards.extend(_search("key in ({})".format(",".join(chunk))))
    return cards, invalid_keys
