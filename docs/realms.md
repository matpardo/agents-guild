# Realms

Back to the [README](../README.md).

## Realms

A realm connects guilds on one network. Any machine can run the hub, including one that runs a guild; the hub is a file store with no database, and it never reads or writes `guild.db`.

```
guild realm init --name <realm> --bind <addr> --port <n>   # config + self-signed certificate; prints the SHA-256 fingerprint
guild realm serve                           # serve the hub over https
guild realm member add <name>               # prints the member token once and the join line
guild realm member list                     # member names only
guild realm member remove <name>            # drops the member and its stored status
```

`init` names the realm and writes `realm-hub.json` (0600) under the guild config dir and a
certificate and key (0600) in `realm-hub/` beside it. Give each member the
fingerprint and its token over a channel you trust; the token is shown once and
only its SHA-256 hash is stored on the hub.

The hub stores, under `realm-hub/` in the guild data dir (0700), one
`status/<guild>.json` per guild and an `inbox/<guild>/` folder of md files
with their metadata. Routes (all need `Authorization: Bearer <token>`):
`PUT /status`, `GET /status` (with the realm name), `GET /whoami` (the token's member and the realm name), `POST /inbox/<guild>`, `GET /inbox`,
`GET /inbox/<id>` and `DELETE /inbox/<id>`. The sender is always the member of
the token, never a field of the body. A status body is capped at 16 KB, a file
at 256 KB, an inbox at 100 files.

Joining a realm:

```
guild realm member add <name>                                  # on the hub: prints the token once and the join line
guild realm join <url> --fingerprint <F>                       # on the guild: asks for the token at a prompt
guild realm push                                               # send this guild's counts to the hub
guild realm status                                             # every guild's counts; refreshes the cache
guild realm status --cached                                    # last fetched status, no network
guild realm send <guild> <file.md>                             # put an md file in another guild's inbox
guild realm inbox                                              # files waiting for this guild; refreshes the inbox cache
guild realm fetch <id> [--out <dir>]                           # save one file for you to read
guild realm drop <id>                                          # delete one file from the hub
guild realm doctor                                             # check the link to the hub and the hub itself
```

Name the guild first: put `"name"` in `guild.json` (see Global config). The
member name on the hub must be that name. `member add` ends with the line to run
on the guild, `guild realm join https://<addr>:<port> --fingerprint <F>`
(`<hub-address>` when the hub binds to every address); it never repeats the token.
`join` reads the token with a hidden prompt (never argv), asks the hub who the
token belongs to (`/whoami`), refuses when that member is not this guild's name,
and only then writes `realm.json` with the realm name; a `realm.json` from before
names needs `join --force`. It checks the hub with the
pinned fingerprint and writes `realm.json` (0600) under the guild
config dir; `--force` replaces an existing one. The client compares the
certificate fingerprint before it sends anything, so the token never reaches a
wrong server. `status` keeps the last reply in `realm-cache.json` (0600) in the
data dir and drops entries that fail validation, saying how many. `guild doctor`
checks the mode and shape of `realm.json`.

The status holds, per project: parties, open quests, open PRs, ready PRs, open
asks and whether main is red (a main blocked only by billing does not count).
`push` is meant for a timer; every 5 minutes with cron:

```
*/5 * * * * guild realm push
```

or a systemd user timer with `OnUnitActiveSec=5min` running `guild realm push`.

Sending and receiving files: `send` takes a regular `.md` file of at most 256 KB,
valid UTF-8, and prints the id the hub gave it; the hub names the file and the
receiver sees the sending guild from the token, never from the file. `inbox`
lists id, sender, name, size and age, and keeps the list in
`realm-inbox-cache.json` (0600) in the guild data dir for the board. `fetch`
writes the file as `<name>` (or `<name-stem>-<id>.md` when that name exists) with
mode 0600 into `--out`, which defaults to `realm-files/` in the guild data dir
(0700); `fetch` creates a missing `--out` folder as 0700 and never changes the mode of an
existing one; it prints the path and the sender, and the file stays on the hub until
`drop`. When the text looks like an instruction or a command, `fetch` adds the
flag line and tells you to read it yourself before giving it to an agent. The
rule is: a human reads a realm file first; nothing injects a realm file or the
inbox into a session, and agents are denied `send`, `inbox`, `fetch` and `drop`.

The web board shows a Realm panel in the overview view once `realm.json`
exists: per guild, how long ago it was last seen and, per project, the counts
with a red marker when main is red. It reads the cached status, never the
network; its Refresh button runs the same call as `guild realm status` and
redraws the panel, showing the error text when the hub is unreachable or its
fingerprint changed. The panel also has an Inbox list (sender, name, size,
age) with Refresh inbox, Fetch and Drop buttons; Drop asks for confirmation,
Fetch saves into the default `realm-files/` dir and shows the saved path and the
flag when the text looks like an instruction, and Refresh also reloads the
inbox.
Its Check button runs the same checks as `guild realm doctor` and lists the
lines, failures marked in red and warnings muted.

`guild realm doctor` only reads: it prints `ok      ...`, `warn    ...` and
`fail    ...` lines like `guild doctor` and exits 1 when any check fails (warnings
do not fail); agents may run it. On a guild with `realm.json` it checks, in
order, and a failure stops the checks that depend on it: the file mode (0600) and
shape of `realm.json`; that the hub is reachable, answers a TLS 1.3 handshake and
shows the pinned fingerprint; that the hub accepts the token (`/whoami`), that
the token belongs to this guild and that the hub still calls the realm by the
name this guild joined; that the clock differs from the hub's `Date` header by at
most 2 minutes (`warn`); and that this guild pushed (`warn` when it never did, or
when the last push is over 15 minutes old: is the push timer running?). Without
`realm.json` it prints `ok      no realm joined`. On the machine that runs the hub
(`realm-hub.json` exists) it also checks the modes of the config and the key
(0600) and of the pki and store dirs (0700); the certificate end date with
`openssl x509 -enddate` (`warn` under 30 days or without `openssl`, `fail` once
expired); and, per member, the age of its stored status (`warn` when it never
pushed or pushed over 1 hour ago).

To keep the hub running, a systemd user unit,
`~/.config/systemd/user/guild-realm.service`:

```
[Unit]
Description=Guild realm hub

[Service]
ExecStart=%h/.local/bin/guild realm serve
Restart=on-failure

[Install]
WantedBy=default.target
```

then `systemctl --user daemon-reload` and `systemctl --user enable --now guild-realm`.

Security:

- The certificate is self-signed and pinned by its fingerprint; TLS 1.3 only. A downgrade or a plain-HTTP peer fails with its own error (`realm hub refused the TLS 1.3 handshake`) before the token is sent.
- Tokens are compared in constant time and stored hashed.
- The status carries counts and booleans only (per project: parties, open quests, open PRs, ready PRs, open asks, red main), validated strictly; no free text crosses in it.
- Agents may run `guild realm status` only: every other `guild realm` command refuses when `CLAUDECODE` is set, and a hook denies them too. Both are defence in depth, not a sandbox (the same known limit as ask answers).
- The hub drops connections past 32 at once, closes any connection that has not finished its TLS handshake and request headers within 10 seconds (so stalled sockets cannot hold every slot), caps a sender at 20 files per inbox, and removing a member deletes its status and inbox.
