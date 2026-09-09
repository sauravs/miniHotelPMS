# -*- coding: utf-8 -*-
"""
THE ONLY FILE IN THE ENGINE THAT KNOWS A SOCKET EXISTS.

    python3 -m hotelcontrols.web.server        ->  http://127.0.0.1:8765/

Eleven lines of work around `handle(path)`, and that ratio is the point. Everything worth
testing is in `app.py` and `render.py` as pure functions of a string, so the suite asserts the
whole demo without binding a port - and this file cannot hide a decision, because it makes none.

It LISTENS. It never dials out: there is no HTTP client anywhere in this engine (criterion 11),
and `tests/unit/test_stdlib_only.py` exempts this one path by name for the listening half while
still forbidding the outbound half everywhere.

Bound to 127.0.0.1 by default and not to 0.0.0.0. This demo has no authentication - that is
scoped out in `prd.md` - and it renders pseudonymised guest data. A demo that listened on every
interface would be a demo that published it.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer

from .app import App

HOST, PORT = "127.0.0.1", 8765

# SERIAL, not threading, and this is a correctness decision rather than a simplification. The
# run store is one `sqlite3` connection opened when the app is built, and a connection may only
# be used from the thread that made it - so a threading server answered its first run page with
# `500 ProgrammingError: SQLite objects created in a thread can only be used in that same
# thread`, with the entire suite green. Nothing in the suite had ever crossed a thread, because
# `handle(path)` is a pure function of a string and that is what makes it testable at all.
#
# A single-operator local demo has nothing to gain from concurrency, and `check_same_thread=
# False` would have turned an exception into a data race. If this is ever made threaded, the
# store has to become thread-safe first.
SERVER = HTTPServer


# The page loads no script and no external resource, so it can say so - and a demo that renders
# guest names supplied by booking channels is exactly where an injected <script> would matter.
# Every value is escaped on the way in (`render._e`); this is the second lock on the same door.
SECURITY_POLICY = "default-src 'none'; style-src 'self'; img-src 'self'"


def respond(app: App, path: str) -> tuple[int, dict[str, str], bytes]:
    """One request, as a value: status, headers, body bytes.

    Extracted from the handler so the socket half of this file is six lines that decide
    nothing. Everything worth asserting - the status, the content type, the byte length, the
    encoding, the policy header - is asserted here, without binding a port.
    """
    status, content_type, body = app.handle(path)
    payload = body.encode("utf-8")
    headers = {
        "Content-Type": content_type,
        "Content-Length": str(len(payload)),
        "Content-Security-Policy": SECURITY_POLICY,
    }
    return status, headers, payload


class Handler(BaseHTTPRequestHandler):
    """One method, and it is GET. This engine is read-only, permanently (`prd.md` §6)."""

    app = App()
    server_version = "hotelcontrols"

    def do_GET(self) -> None:                                          # noqa: N802
        status, headers, payload = respond(self.app, self.path)
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:
        """Quieter than the default, and it never logs a query string.

        `?property=` and `?evidence=` are harmless, but a log line is the easiest place for
        data to leak out of a system that was careful everywhere else.
        """
        print("%s %s" % (self.command, self.path.split("?")[0]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the control engine demo, offline.")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    arguments = parser.parse_args()

    server = SERVER((arguments.host, arguments.port), Handler)
    print("Controls at http://%s:%d/ - no network access, no dependencies, ctrl-c to stop."
          % (arguments.host, arguments.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
