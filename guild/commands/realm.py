import getpass
import json
import os
import secrets
import shutil
import subprocess

from guild import names, paths, timeutil
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


def init(bind, port, claudecode):
    _require_human(claudecode)
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
        {"bind": bind, "port": port, "cert": str(cert_path), "key": str(key_path), "members": {}}
    )
    return "realm hub initialized on {}:{}\ncertificate fingerprint (SHA-256): {}".format(
        bind, port, pin.cert_fingerprint(cert_path)
    )


def serve(claudecode):
    _require_human(claudecode)
    return hub.serve_forever(hubconfig.load())


def member_add(name, claudecode):
    _require_human(claudecode)
    names.validate_name(name, "member name")
    config = hubconfig.load()
    if name in config["members"]:
        raise GuildError("member '{}' already exists".format(name), 1)
    token = secrets.token_urlsafe(32)
    config["members"][name] = hub.token_hash(token)
    hubconfig.save(config)
    return "member {} added\ntoken (shown once, store it now): {}".format(name, token)


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


def join(url, fingerprint, guild_name, force, claudecode):
    _require_human(claudecode)
    names.validate_name(guild_name, "guild name")
    client.parse_url(url)
    pinned = clientconfig.normalize_fingerprint(fingerprint)
    if clientconfig.exists() and not force:
        raise GuildError("realm already joined: {} (use --force to replace)".format(paths.realm_config_path()), 1)
    token = getpass.getpass("realm token: ").strip()
    if not token:
        raise GuildError("empty token", 1)
    candidate = {"url": url, "fingerprint": pinned, "guild": guild_name, "token": token}
    client.request(candidate, "GET", "/status", None)
    clientconfig.save(candidate)
    return "joined realm {} as {}".format(url, guild_name)


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
    payload = client.request(clientconfig.load(), "GET", "/status", None)
    entries = payload.get("guilds")
    if not isinstance(entries, list):
        raise GuildError("realm hub sent an invalid response", 1)
    valid = _valid_entries(entries)
    model = {"fetched_at": timeutil.to_iso(ctx.now), "guilds": valid}
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
        guilds = _valid_entries(cached["guilds"])
    except (ValueError, KeyError, TypeError):
        raise GuildError("realm cache is malformed: {}".format(path), 1)
    return {"fetched_at": fetched_at, "guilds": guilds, "dropped": 0}


def _project_line(project):
    return "  {name}: parties {parties}, quests {open_quests}, PRs {open_prs} ({ready_prs} ready), asks {open_asks}{red}".format(
        red=", main red" if project["main_red"] else "", **project
    )


def render_status(model, now):
    lines = ["realm status fetched {} ago".format(timeutil.age_label(now, model["fetched_at"]))]
    if model["dropped"]:
        lines.append("dropped {} invalid entr{}".format(model["dropped"], "y" if model["dropped"] == 1 else "ies"))
    for guild_entry in model["guilds"]:
        lines.append("{} (last seen {} ago)".format(guild_entry["guild"], timeutil.age_label(now, guild_entry["received_at"])))
        lines.extend(_project_line(project) for project in guild_entry["projects"])
    return "\n".join(lines)


def show_status(ctx, cached):
    model = cached_status_model() if cached else realm_status_model(ctx)
    return render_status(model, ctx.now)
