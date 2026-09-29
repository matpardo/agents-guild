from guild import webserver


def run(port):
    return webserver.serve_forever(port)
