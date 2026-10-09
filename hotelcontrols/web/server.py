# -*- coding: utf-8 -*-
"""
THE ONLY FILE IN THE ENGINE THAT KNOWS A SOCKET EXISTS.

    python3 -m hotelcontrols.web.server                    ->  http://127.0.0.1:8765/
    python3 -m hotelcontrols.web.server --store runs.db    ...keeping history and the queue

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
import html
import logging
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from ..ops import LOGGER_NAME, JsonLines, attach
from ..store import RunStore
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


# How much form body this server will read. A compose turn is a sentence and a couple of
# identifiers; anything past this is not a control being described.
MAX_BODY = 64 * 1024


def respond(app: App, path: str, body: str | None = None) -> tuple[int, dict[str, str], bytes]:
    """One request, as a value: status, headers, body bytes.

    Extracted from the handler so the socket half of this file is six lines that decide
    nothing. Everything worth asserting - the status, the content type, the byte length, the
    encoding, the policy header - is asserted here, without binding a port.

    `body` is None for a GET, which is every route but the two the compose front end adds.
    """
    status, content_type, page = (app.handle(path) if body is None
                                  else app.handle_post(path, body))
    payload = page.encode("utf-8")
    headers = {
        "Content-Type": content_type,
        "Content-Length": str(len(payload)),
        "Content-Security-Policy": SECURITY_POLICY,
    }
    # A 303 is how the compose flow stops a reload from re-filing a draft: the POST answers
    # with "look over there", and the reader's next request is an ordinary GET of the run page.
    if status == 303:
        headers["Location"] = _location(page)
    return status, headers, payload


def _location(page: str) -> str:
    """Where a redirect body points, read back out of the page it rendered.

    Read from the body rather than passed alongside it so that `Response` keeps its three
    fields and every existing `status, content_type, body = ...` unpacking keeps working. A
    page is still a value; this reads one attribute of it.

    It reads the META REFRESH and not an `href`, because the page shell carries an href for the
    stylesheet - "the first href in the body" sent a reader to /style.css, which a test caught.
    The meta refresh appears exactly once and only in a redirect body, and it is also what
    makes the redirect work for a client that ignores the header.
    """
    match = re.search(r'<meta http-equiv="refresh" content="0; url=([^"]+)">', page)
    return html.unescape(match.group(1)) if match else "/"


class Handler(BaseHTTPRequestHandler):
    """GET everywhere, and POST on the two compose routes.

    This engine is still read-only against a PMS, permanently (`prd.md` §6) - it has no client
    that could write to one. What a POST writes is our own `spec/drafts/` directory and our own
    run store, and it exists because filing a draft and asking a model a question are both
    things a link should not do.
    """

    app = App()
    server_version = "hotelcontrols"

    def do_GET(self) -> None:                                          # noqa: N802
        self._reply(respond(self.app, self.path))

    def do_POST(self) -> None:                                         # noqa: N802
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY:
            # Refused without reading it. A body this large is not a rule being described, and
            # reading it first to find that out is the part worth avoiding.
            self._reply(respond(self.app, "/nowhere-this-body-is-too-large"))
            return
        raw = self.rfile.read(length) if length else b""
        self._reply(respond(self.app, self.path, raw.decode("utf-8", errors="replace")))

    def _reply(self, response: tuple[int, dict[str, str], bytes]) -> None:
        status, headers, payload = response
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


def parser() -> argparse.ArgumentParser:
    """The command line, as a value, so the one decision in it can be tested without a port."""
    built = argparse.ArgumentParser(description="Serve the control engine demo, offline.")
    built.add_argument("--host", default=HOST)
    built.add_argument("--port", type=int, default=PORT)
    # Slice 18 (brief §8.8). OPT-IN: the default demo keeps its history and its findings queue
    # in memory, exactly as it always has, and the queue page says they are lost on restart.
    built.add_argument("--store", metavar="PATH", default=None,
                       help="keep the run history and the findings queue in this SQLite file "
                            "(default: in memory, lost on restart)")
    # Slice 20: the operational log, as JSON lines. On by default for the server - somebody
    # running the service should see what ran - and stderr, so it never mixes with a page.
    built.add_argument("--log", metavar="PATH", default="-",
                       help="write the operational log as JSON lines to PATH, '-' for stderr "
                            "(the default) or 'off'")
    return built


def configure_log(target: str) -> logging.Handler | None:
    """Attach the operational log to stderr ("-"), to a file, or to nothing ("off")."""
    if target == "off":
        return None
    if target == "-":
        return attach(sys.stderr)
    handler = logging.FileHandler(target, encoding="utf-8")
    handler.setFormatter(JsonLines())
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return handler


def build_app(store: str | None) -> App:
    """The demo app, with its store in memory unless a file was asked for."""
    return App(store=RunStore(store)) if store else App()


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.store:
        Handler.app = build_app(arguments.store)
    configure_log(arguments.log)

    server = SERVER((arguments.host, arguments.port), Handler)
    print("Controls at http://%s:%d/ - no network access, no dependencies, ctrl-c to stop."
          % (arguments.host, arguments.port))
    print("History and the findings queue are %s." % (
        "kept in %s" % arguments.store if arguments.store
        else "held in memory and lost on restart (--store PATH keeps them)"))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
