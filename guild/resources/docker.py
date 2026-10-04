import json
import os
import re

from guild.resources import sizes

CATEGORY_CONTAINER = "docker_container"
CATEGORY_IMAGE = "docker_image"
CATEGORY_VOLUME = "docker_volume"
MARKER_CATEGORY = "docker"
_TIMEOUT_SECONDS = 60
_DF_VERBOSE_ARGV = ["docker", "system", "df", "-v", "--format", "json"]
_DF_ARGV = ["docker", "system", "df", "--format", "json"]
_PROJECT_RE = re.compile(r"(?:^|,)com\.docker\.compose\.project=([^,]*)")
_WORKING_DIR_RE = re.compile(r"(?:^|,)com\.docker\.compose\.project\.working_dir=([^,]*)")
_NAME_STRIP_RE = re.compile(r"[^a-z0-9_-]")
_HEX_RE = re.compile(r"^[0-9a-f]{12,64}$")
_DANGLING_REPOSITORY = "<none>"
_NO_CONTAINERS = "0"
_SHORT_ID_LENGTH = 12
_ID_PREFIX = "sha256:"
_TOTAL_KEYS = {
    "Images": "images",
    "Containers": "containers",
    "Local Volumes": "volumes",
    "Build Cache": "build_cache",
}


def compose_project(labels):
    return _label_value(_PROJECT_RE, labels)


def compose_working_dir(labels):
    return _label_value(_WORKING_DIR_RE, labels)


def _label_value(pattern, labels):
    if not labels:
        return None
    match = pattern.search(labels)
    if match is None:
        return None
    return match.group(1)


def _failure_reason(result):
    if result["error"] is not None:
        return "not installed"
    if result["timed_out"]:
        return "timeout"
    if result["exit_code"] == 0:
        return None
    stderr = result["stderr"].lower()
    if "permission denied" in stderr:
        return "permission denied"
    if "cannot connect" in stderr:
        return "daemon unreachable"
    return "unparseable"


def _parse_verbose(text):
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _total_line(line):
    try:
        parsed = json.loads(line)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _parse_totals(text):
    totals = {name: None for name in _TOTAL_KEYS.values()}
    totals["images_reclaimable"] = None
    parsed_any = False
    for line in text.splitlines():
        if not line.strip():
            continue
        entry = _total_line(line)
        if entry is None:
            return None
        parsed_any = True
        key = _TOTAL_KEYS.get(entry.get("Type"))
        if key is None:
            continue
        totals[key] = sizes.parse_human_size(entry.get("Size"))
        if key == "images":
            totals["images_reclaimable"] = sizes.parse_human_size(entry.get("Reclaimable"))
    if not parsed_any:
        return None
    return totals


def _unavailable(reason):
    return {"ok": False, "reason": reason, "df": None, "totals": None}


def scan(runner):
    verbose = runner(_DF_VERBOSE_ARGV, _TIMEOUT_SECONDS)
    totals_result = runner(_DF_ARGV, _TIMEOUT_SECONDS)
    for result in (verbose, totals_result):
        reason = _failure_reason(result)
        if reason is not None:
            return _unavailable(reason)
    df = _parse_verbose(verbose["stdout"])
    totals = _parse_totals(totals_result["stdout"])
    if df is None or totals is None:
        return _unavailable("unparseable")
    return {"ok": True, "reason": None, "df": df, "totals": totals}


def _normalize_name(basename):
    return _NAME_STRIP_RE.sub("", basename.lower())


def _is_inside(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


class _Attribution:
    def __init__(self, df, roots_by_project, checkouts_by_project, dir_exists):
        self._roots = roots_by_project
        self._checkouts = checkouts_by_project
        self._dir_exists = dir_exists
        self._containers = [item for item in df.get("Containers", []) if isinstance(item, dict)]
        self._volumes = [item for item in df.get("Volumes", []) if isinstance(item, dict)]
        self._images = [item for item in df.get("Images", []) if isinstance(item, dict)]
        self._compose_dirs = self._collect_compose_dirs()
        self._container_projects = {compose_project(item.get("Labels")) for item in self._containers}
        self._container_projects.discard(None)
        self._known_names = self._container_projects | self._volume_project_names()

    def _collect_compose_dirs(self):
        directories = {}
        for container in self._containers:
            name = compose_project(container.get("Labels"))
            working_dir = compose_working_dir(container.get("Labels"))
            if name is not None and working_dir is not None:
                directories.setdefault(name, working_dir)
        return directories

    def _volume_project_names(self):
        names = {compose_project(volume.get("Labels")) for volume in self._volumes}
        names.discard(None)
        return names

    def owner_of(self, path):
        best = None
        for project in sorted(self._roots):
            for root in self._roots[project]:
                if not _is_inside(path, root):
                    continue
                if best is None or len(root) > best[0]:
                    best = (len(root), project)
        if best is None:
            return None
        return best[1]

    def _checkout_owner_named(self, name):
        for project in sorted(self._checkouts):
            for path in self._checkouts[project]:
                if self._dir_exists(path) and _normalize_name(os.path.basename(path)) == name:
                    return project
        return None

    def orphaned(self, name):
        working_dir = self._compose_dirs.get(name)
        if working_dir is not None and not self._dir_exists(working_dir):
            return True
        return name not in self._container_projects and self._checkout_owner_named(name) is None

    def owner_of_compose_name(self, name):
        working_dir = self._compose_dirs.get(name)
        if working_dir is not None:
            return self.owner_of(working_dir)
        return self._checkout_owner_named(name)

    def container_owner(self, container):
        working_dir = compose_working_dir(container.get("Labels"))
        if working_dir is None:
            return None
        return self.owner_of(working_dir)

    def containers(self):
        return self._containers

    def volumes(self):
        return self._volumes

    def images(self):
        return self._images

    def known_names(self):
        return self._known_names

    def compose_dirs(self):
        return self._compose_dirs


def _size_fields(text):
    size = sizes.parse_human_size(text)
    if size is None:
        return None, "unavailable"
    return size, "ok"


def _strip_id_prefix(identifier):
    if identifier.startswith(_ID_PREFIX):
        return identifier[len(_ID_PREFIX):]
    return identifier


def _short_id(identifier):
    return _strip_id_prefix(identifier or "")[:_SHORT_ID_LENGTH]


def _container_row(attribution, container):
    labels = container.get("Labels")
    name = compose_project(labels)
    names = container.get("Names") or ""
    item = names.split(",")[0] or _short_id(container.get("ID"))
    size, state = _size_fields(container.get("Size"))
    flag = "orphaned" if name is not None and attribution.orphaned(name) else ""
    owner = attribution.container_owner(container)
    return owner, [CATEGORY_CONTAINER, item, size, state, flag, name or ""]


def _volume_row(attribution, volume):
    name = compose_project(volume.get("Labels"))
    size, state = _size_fields(volume.get("Size"))
    owner, flag = _volume_owner_and_flag(attribution, name)
    return owner, [CATEGORY_VOLUME, volume.get("Name") or "", size, state, flag, name or ""]


def _volume_owner_and_flag(attribution, name):
    if name is None:
        return None, ""
    owner = attribution.owner_of_compose_name(name)
    if name in attribution.compose_dirs():
        return owner, "orphaned" if attribution.orphaned(name) else ""
    if owner is not None:
        return owner, ""
    return None, "orphaned"


def _image_references(image):
    repository = image.get("Repository") or ""
    tag = image.get("Tag") or ""
    return {repository, "{}:{}".format(repository, tag)}


def _image_matches(image, container):
    reference = container.get("Image") or ""
    if reference in _image_references(image):
        return True
    cleaned = _strip_id_prefix(reference)
    if not _HEX_RE.match(cleaned):
        return False
    return _strip_id_prefix(image.get("ID") or "").startswith(cleaned)


def _image_item(image):
    repository = image.get("Repository") or ""
    if repository == _DANGLING_REPOSITORY:
        return _short_id(image.get("ID"))
    return "{}:{}".format(repository, image.get("Tag") or "")


def _name_prefix_match(attribution, repository):
    matches = [name for name in attribution.known_names() if repository.startswith(name + "-")]
    if not matches:
        return None
    return max(matches, key=len)


def _fallback_flag(image):
    if image.get("Repository") == _DANGLING_REPOSITORY:
        return "dangling"
    if image.get("Containers") == _NO_CONTAINERS:
        return "unused"
    return ""


def _image_owner_and_flag(attribution, image):
    matched = [container for container in attribution.containers() if _image_matches(image, container)]
    if matched:
        owners = {attribution.container_owner(container) for container in matched}
        owner = owners.pop() if len(owners) == 1 else None
        names = [compose_project(container.get("Labels")) for container in matched]
        all_orphaned = all(name is not None and attribution.orphaned(name) for name in names)
        return owner, "orphaned" if all_orphaned else ""
    name = _name_prefix_match(attribution, image.get("Repository") or "")
    if name is not None:
        return attribution.owner_of_compose_name(name), "orphaned" if attribution.orphaned(name) else ""
    return None, _fallback_flag(image)


def _image_row(attribution, image):
    size, state = _size_fields(image.get("UniqueSize"))
    owner, flag = _image_owner_and_flag(attribution, image)
    return owner, [CATEGORY_IMAGE, _image_item(image), size, state, flag, ""]


def attribute(df, roots_by_project, checkouts_by_project, dir_exists):
    attribution = _Attribution(df, roots_by_project, checkouts_by_project, dir_exists)
    located = [_container_row(attribution, item) for item in attribution.containers()]
    located.extend(_volume_row(attribution, item) for item in attribution.volumes())
    located.extend(_image_row(attribution, item) for item in attribution.images())
    grouped = {}
    for owner, row in located:
        grouped.setdefault(owner, []).append(row)
    return {owner: sorted(rows, key=lambda row: (row[0], row[1])) for owner, rows in grouped.items()}
