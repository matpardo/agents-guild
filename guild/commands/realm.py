import os
import secrets
import shutil
import subprocess

from guild import names, paths
from guild.errors import GuildError
from guild.realm import hub, hubconfig, pin


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
