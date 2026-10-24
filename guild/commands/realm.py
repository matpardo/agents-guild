import getpass
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
from pathlib import Path

from guild import config, names, paths, pii, timeutil
from guild.errors import GuildError
from guild.realm import client, clientconfig, hub, hubconfig, pin, snapshot, status


def _require_human(claudecode):
    if claudecode:
        raise GuildError(
            "realm commands other than status are for the human; run them from your own terminal", 1
        )


def _check_port(port):
    if not 1 <= port <= 65535:
        raise GuildError("invalid port {}: use 1-65535".format(port), 1)


def _generate_cert(cert_path, key_path):
    openssl = shutil.which("openssl")
    if openssl is None:
        raise GuildError("openssl not found on PATH: install it to create the hub certificate", 1)
    result = subprocess.run(
        [
            openssl, "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
            "-nodes", "-days", "3650", "-subj", "/CN=guild-realm",
            "-keyout", str(key_path), "-out", str(cert_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GuildError("openssl failed to create the hub certificate", 1)
    os.chmod(key_path, 0o600)
    os.chmod(cert_path, 0o600)


def init(name, bind, port, claudecode):
    _require_human(claudecode)
    names.validate_name(name, "realm name")
    if not bind or bind != bind.strip():
        raise GuildError("invalid bind address", 1)
    _check_port(port)
    if hubconfig.exists():
        raise GuildError("realm hub already initialized: {}".format(paths.realm_hub_config_path()), 1)
    pki_dir = paths.ensure_private_dir(paths.realm_hub_pki_dir())
    cert_path = pki_dir / "cert.pem"
    key_path = pki_dir / "key.pem"
    _generate_cert(cert_path, key_path)
    hubconfig.save(
        {"name": name, "bind": bind, "port": port, "cert": str(cert_path), "key": str(key_path), "members": {}}
    )
    return "realm {} initialized on {}:{}\ncertificate fingerprint (SHA-256): {}".format(
        name, bind, port, pin.cert_fingerprint(cert_path)
    )


def serve(claudecode):
    _require_human(claudecode)
    return hub.serve_forever(hubconfig.load())


def _join_url(hub_config):
    address = hub_config["bind"]
    if address in ("", "0.0.0.0", "::"):
        address = "<hub-address>"
    elif ":" in address:
        address = "[{}]".format(address)
    return "https://{}:{}".format(address, hub_config["port"])


def member_add(name, claudecode):
    _require_human(claudecode)
    names.validate_name(name, "member name")
    config = hubconfig.load()
    if name in config["members"]:
        raise GuildError("member '{}' already exists".format(name), 1)
    token = secrets.token_urlsafe(32)
    config["members"][name] = hub.token_hash(token)
    hubconfig.save(config)
    return "member {} added\ntoken (shown once, store it now): {}\njoin on the guild with: guild realm join {} --fingerprint {}".format(
        name, token, _join_url(config), pin.cert_fingerprint(Path(config["cert"]))
    )


def member_list(claudecode):
    _require_human(claudecode)
    return sorted(hubconfig.load()["members"])


def member_remove(name, claudecode):
    _require_human(claudecode)
    names.validate_name(name, "member name")
    config = hubconfig.load()
    if name not in config["members"]:
        raise GuildError("unknown member '{}'".format(name), 1)
    del config["members"][name]
    hubconfig.save(config)
    status_file = paths.realm_hub_store_dir() / "status" / (name + ".json")
    status_file.unlink(missing_ok=True)
    shutil.rmtree(paths.realm_hub_store_dir() / "inbox" / name, ignore_errors=True)
    return "member {} removed".format(name)


def _is_valid_name(value):
    if not isinstance(value, str):
        return False
    try:
        names.validate_name(value, "name")
    except GuildError:
        return False
    return True


def suggested_guild_name():
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", socket.gethostname()).strip("-.")
    return slug or "guild"


def missing_name_hint():
    return 'set "name" in {} (suggested: {})'.format(paths.global_config_path(), suggested_guild_name())


def join(url, fingerprint, force, claudecode):
    _require_human(claudecode)
    guild_name = config.load_global(paths.global_config_path()).get("name")
    if guild_name is None:
        raise GuildError("this guild has no name: " + missing_name_hint(), 1)
    client.parse_url(url)
    pinned = clientconfig.normalize_fingerprint(fingerprint)
    if clientconfig.exists() and not force:
        raise GuildError("realm already joined: {} (use --force to replace)".format(paths.realm_config_path()), 1)
    token = getpass.getpass("realm token: ").strip()
    if not token:
        raise GuildError("empty token", 1)
    candidate = {"url": url, "fingerprint": pinned, "guild": guild_name, "token": token}
    identity = client.request(candidate, "GET", "/whoami", None)
    member = identity.get("member")
    realm = identity.get("realm")
    if not _is_valid_name(member) or not _is_valid_name(realm):
        raise GuildError("realm hub sent an invalid response", 1)
    if member != guild_name:
        raise GuildError("the token belongs to {}, this guild is {}".format(member, guild_name), 1)
    candidate["realm"] = realm
    clientconfig.save(candidate)
    return "joined realm {} at {} as {}".format(realm, url, guild_name)


def push(ctx, claudecode):
    _require_human(claudecode)
    config = clientconfig.load()
    body = snapshot.build(ctx, config["guild"])
    client.request(config, "PUT", "/status", body)
    return "pushed status of {} project(s) to {}".format(len(body["projects"]), config["url"])


def _valid_entries(entries):
    valid = []
    for entry in entries:
        try:
            valid.append(status.validate(entry, True))
        except GuildError:
            continue
    return valid


def _write_cache(model):
    path = paths.realm_cache_path()
    paths.ensure_private_dir(path.parent)
    hubconfig.write_atomic(path, json.dumps(model).encode("utf-8"))


def realm_status_model(ctx):
    joined = clientconfig.load()
    payload = client.request(joined, "GET", "/status", None)
    entries = payload.get("guilds")
    realm = payload.get("realm")
    if not isinstance(entries, list) or not _is_valid_name(realm):
        raise GuildError("realm hub sent an invalid response", 1)
    if realm != joined["realm"]:
        raise GuildError(
            "the hub now calls its realm {}, this guild joined {}: re-run join --force".format(realm, joined["realm"]), 1
        )
    valid = _valid_entries(entries)
    model = {"fetched_at": timeutil.to_iso(ctx.now), "realm": realm, "guilds": valid}
    _write_cache(model)
    return dict(model, dropped=len(entries) - len(valid))


def cached_status_model():
    path = paths.realm_cache_path()
    if not path.exists():
        raise GuildError("no cached realm status: run status online first", 1)
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = cached["fetched_at"]
        timeutil.from_iso(fetched_at)
        realm = cached["realm"]
        guilds = _valid_entries(cached["guilds"])
    except (ValueError, KeyError, TypeError):
        raise GuildError("realm cache is malformed: {}".format(path), 1)
    if not _is_valid_name(realm):
        raise GuildError("realm cache is malformed: {}".format(path), 1)
    return {"fetched_at": fetched_at, "realm": realm, "guilds": guilds, "dropped": 0}


def _project_line(project):
    return "  {name}: parties {parties}, quests {open_quests}, PRs {open_prs} ({ready_prs} ready), asks {open_asks}{red}".format(
        red=", main red" if project["main_red"] else "", **project
    )


def render_status(model, now):
    lines = [
        "realm {}".format(model["realm"]),
        "realm status fetched {} ago".format(timeutil.age_label(now, model["fetched_at"])),
    ]
    if model["dropped"]:
        lines.append("dropped {} invalid entr{}".format(model["dropped"], "y" if model["dropped"] == 1 else "ies"))
    for guild_entry in model["guilds"]:
        lines.append("{} (last seen {} ago)".format(guild_entry["guild"], timeutil.age_label(now, guild_entry["received_at"])))
        lines.extend(_project_line(project) for project in guild_entry["projects"])
    return "\n".join(lines)


def show_status(ctx, cached):
    model = cached_status_model() if cached else realm_status_model(ctx)
    return render_status(model, ctx.now)


_MAX_FIELD_LENGTH = 64
_MAX_ISO_LENGTH = 64
_FILE_KEYS = frozenset(("id", "from", "name", "size", "sent_at"))


def _is_bounded_text(value):
    return isinstance(value, str) and 0 < len(value) <= _MAX_FIELD_LENGTH + len(".md")


def _is_valid_sender(value):
    if not isinstance(value, str) or len(value) > _MAX_FIELD_LENGTH:
        return False
    try:
        names.validate_name(value, "guild name")
    except GuildError:
        return False
    return True


def _is_valid_iso(value):
    if not isinstance(value, str) or len(value) > _MAX_ISO_LENGTH:
        return False
    try:
        timeutil.from_iso(value)
    except ValueError:
        return False
    return True


def _is_valid_file(entry):
    if not isinstance(entry, dict) or set(entry) != _FILE_KEYS:
        return False
    size = entry["size"]
    return (
        isinstance(entry["id"], str)
        and hub.is_file_id(entry["id"])
        and _is_valid_sender(entry["from"])
        and _is_bounded_text(entry["name"])
        and isinstance(size, int)
        and not isinstance(size, bool)
        and 0 <= size <= hub.CONTENT_MAX_BYTES
        and _is_valid_iso(entry["sent_at"])
    )


def _valid_files(entries):
    return [entry for entry in entries if _is_valid_file(entry)]


def _read_local_markdown(file_path):
    path = Path(file_path)
    if path.suffix != ".md":
        raise GuildError("only .md files can be sent: {}".format(file_path), 1)
    if not path.is_file():
        raise GuildError("not a regular file: {}".format(file_path), 1)
    with path.open("rb") as handle:
        data = handle.read(hub.CONTENT_MAX_BYTES + 1)
    if len(data) > hub.CONTENT_MAX_BYTES:
        raise GuildError("file too large: limit is {} bytes".format(hub.CONTENT_MAX_BYTES), 1)
    try:
        return path.name, data.decode("utf-8")
    except UnicodeDecodeError:
        raise GuildError("file is not valid UTF-8: {}".format(file_path), 1)


def send(target_guild, file_path, claudecode):
    _require_human(claudecode)
    names.validate_name(target_guild, "guild name")
    name, content = _read_local_markdown(file_path)
    payload = client.request(
        clientconfig.load(), "POST", "/inbox/" + target_guild, {"name": name, "content": content}
    )
    file_id = payload.get("id")
    if not isinstance(file_id, str) or not hub.is_file_id(file_id):
        raise GuildError("realm hub sent an invalid response", 1)
    return "sent {} to {} as {}".format(name, target_guild, file_id)


def _write_inbox_cache(model):
    path = paths.realm_inbox_cache_path()
    paths.ensure_private_dir(path.parent)
    hubconfig.write_atomic(path, json.dumps(model).encode("utf-8"))


def inbox_model(ctx, claudecode):
    _require_human(claudecode)
    payload = client.request(clientconfig.load(), "GET", "/inbox", None)
    entries = payload.get("files")
    if not isinstance(entries, list):
        raise GuildError("realm hub sent an invalid response", 1)
    model = {"fetched_at": timeutil.to_iso(ctx.now), "files": _valid_files(entries)}
    _write_inbox_cache(model)
    return model


def cached_inbox():
    path = paths.realm_inbox_cache_path()
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        timeutil.from_iso(cached["fetched_at"])
        return _valid_files(cached["files"])
    except (OSError, ValueError, KeyError, TypeError):
        return []


def render_inbox(model, now):
    if not model["files"]:
        return "inbox empty"
    return "\n".join(
        "{} from {} {} {} bytes {} ago".format(
            entry["id"], entry["from"], entry["name"], entry["size"], timeutil.age_label(now, entry["sent_at"])
        )
        for entry in model["files"]
    )


def _checked_file(payload):
    content = payload.get("content")
    sender = payload.get("from")
    name = payload.get("name")
    if not (isinstance(content, str) and _is_valid_sender(sender) and isinstance(name, str)):
        raise GuildError("realm hub sent an invalid response", 1)
    try:
        data = content.encode("utf-8")
    except UnicodeEncodeError:
        raise GuildError("realm file is not valid UTF-8", 1)
    if payload.get("size") != len(data) or len(data) > hub.CONTENT_MAX_BYTES:
        raise GuildError("realm file size does not match its content", 1)
    return sender, hub.safe_name(name), data


def _create_exclusive(directory, file_name, data):
    target = directory / file_name
    if target.name != file_name or target.parent != directory:
        raise GuildError("realm file name escapes the output directory", 1)
    descriptor = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
    return target


def _save_file(directory, file_name, file_id, data):
    try:
        return _create_exclusive(directory, file_name, data)
    except FileExistsError:
        pass
    alternate = "{}-{}.md".format(file_name[: -len(".md")], file_id)
    try:
        return _create_exclusive(directory, alternate, data)
    except FileExistsError:
        raise GuildError("realm file already saved: {}".format(directory / alternate), 1)


def _check_file_id(file_id):
    if not hub.is_file_id(file_id):
        raise GuildError("invalid file id: expected 16 hex characters", 1)


def fetch(file_id, out_dir, claudecode):
    _require_human(claudecode)
    _check_file_id(file_id)
    payload = client.request(clientconfig.load(), "GET", "/inbox/" + file_id, None)
    sender, file_name, data = _checked_file(payload)
    directory = paths.ensure_private_dir(Path(out_dir)).resolve()
    saved = _save_file(directory, file_name, file_id, data)
    return {"path": str(saved), "from": sender, "flagged": pii.looks_instruction_like(data.decode("utf-8"))}


def render_fetch(result):
    lines = ["saved {} from {}".format(result["path"], result["from"])]
    if result["flagged"]:
        lines.append("{} read it yourself before giving it to an agent".format(pii.INSTRUCTION_LIKE_FLAG))
    return "\n".join(lines)


def drop(file_id, claudecode):
    _require_human(claudecode)
    _check_file_id(file_id)
    client.request(clientconfig.load(), "DELETE", "/inbox/" + file_id, None)
    return "dropped {} from the realm inbox".format(file_id)
