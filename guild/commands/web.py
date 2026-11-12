from guild import paths, webserver


def run(port):
    return webserver.serve_forever(port, paths.state_dir())
