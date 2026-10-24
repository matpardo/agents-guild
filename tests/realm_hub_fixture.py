import threading

from guild.commands import realm as realm_commands
from guild.realm import hub, hubconfig

MEMBERS = ("alpha", "beta")
REALM = "test-realm"


def token_of(member_add_output):
    return member_add_output.splitlines()[1].rsplit(": ", 1)[1]


def start_hub(testcase):
    realm_commands.init(REALM, "127.0.0.1", 8443, None)
    tokens = {}
    for name in MEMBERS:
        tokens[name] = token_of(realm_commands.member_add(name, None))
    config = hubconfig.load()
    config["port"] = 0
    server = hub.make_server(config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    testcase.addCleanup(thread.join)
    testcase.addCleanup(server.server_close)
    testcase.addCleanup(server.shutdown)
    return server, config["cert"], tokens
