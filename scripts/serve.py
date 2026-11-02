#!/usr/bin/env python3
"""Preview the site locally:  python3 scripts/serve.py [port]   then open http://localhost:8001

Unlike `python3 -m http.server`, it only listens on this computer (not the local network) and
queues enough connections that a page full of photos doesn't drop requests.
"""
import functools
import http.server
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'  # reuse connections between requests

    def log_message(self, format, *args):
        pass


class Server(http.server.ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    handler = functools.partial(Handler, directory=str(REPO))
    with Server(('127.0.0.1', port), handler) as server:
        print(f'Previewing {REPO} at http://localhost:{port}/  (Ctrl+C to stop)', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
