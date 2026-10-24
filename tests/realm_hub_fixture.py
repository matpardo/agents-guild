import threading

from guild.commands import realm as realm_commands
from guild.realm import hub, hubconfig

MEMBERS = ("alpha", "beta")


def start_hub(testcase):
    realm_commands.init("127.0.0.1", 8443, None)
    tokens = {}
    for name in MEMBERS:
        tokens[name] = realm_commands.member_add(name, None).rsplit(": ", 1)[1]
    config = hubconfig.load()
    config["port"] = 0
    server = hub.make_server(config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    testcase.addCleanup(thread.join)
    testcase.addCleanup(server.server_close)
    testcase.addCleanup(server.shutdown)
    return server, config["cert"], tokens
