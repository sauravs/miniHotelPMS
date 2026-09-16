# -*- coding: utf-8 -*-
"""
THE DEMO, WITH THE COMPOSE FRONT END WIRED.

    python3 -m tools.serve --llm stub     fixed replies, nothing to install, no network
    python3 -m tools.serve --llm local    a model on this machine. FREE           <- default
    python3 -m tools.serve --llm claude   the hosted API. Paid, needs `anthropic`
    python3 -m tools.serve --llm off      identical to the plain server

WHY THIS FILE EXISTS AT ALL, RATHER THAN A FLAG ON THE SERVER
--------------------------------------------------------------
Because this is where the dependency arrow has to turn around. `hotelcontrols/` imports only
the standard library and contains no outbound HTTP client (criterion 11, asserted over the AST
by two separate tests). A model client is exactly the thing that would break that - so the
client lives under `tools/`, this file constructs it, and the app receives it as a parameter.

The engine therefore never imports a backend, never looks one up, and cannot acquire one by
accident. `python3 -m hotelcontrols.web.server` still builds an `App()` with no proposer and
behaves exactly as it always has, which is what keeps the existing suite meaningful.

TWO LOCKS, AND THIS IS THE FIRST HALF OF ONE
---------------------------------------------
A live backend refuses to answer unless `HOTELCONTROLS_COMPOSE=1` is set AND no test runner is
loaded in the process. This launcher does not bypass either; it reports the state of the first
one at startup so a reader is not left wondering why the chat window keeps refusing.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from hotelcontrols.web.app import App
from hotelcontrols.web.server import HOST, PORT, SERVER, Handler

from . import proposers

DRAFT_DIR = pathlib.Path(__file__).resolve().parents[1] / "spec" / "drafts"


def say(message: str) -> None:
    """Print, and flush. Stdout is block-buffered when it is a pipe rather than a terminal, so
    `python3 -m tools.serve > log &` showed an EMPTY log while the server ran perfectly - which
    hid the one line that says whether compose is armed."""
    print(message, flush=True)


def build_app(backend: str, draft_dir: pathlib.Path = DRAFT_DIR) -> App:
    """The demo app, with a proposer if one was asked for."""
    proposer = proposers.build(backend)
    if proposer is not None:
        # Made here rather than on first write: a chat window that accepts a sentence and then
        # cannot file it has wasted the only expensive step in the flow.
        (draft_dir / "ir").mkdir(parents=True, exist_ok=True)
    return App(proposer=proposer, draft_dir=draft_dir if proposer is not None else None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve the control engine demo, with the compose front end.")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--llm", default=proposers.DEFAULT, choices=proposers.NAMES,
                        help="which backend drafts a sentence (default: %(default)s)")
    arguments = parser.parse_args(argv)

    try:
        app = build_app(arguments.llm)
    except RuntimeError as exc:
        # A missing package or an unreachable host is a setup problem with a known fix, and the
        # backend itself already explains it. Printed and exited rather than raised, because a
        # traceback here says nothing a reader can act on.
        print("Could not start the %s backend:\n\n%s" % (arguments.llm, exc), file=sys.stderr)
        return 2

    Handler.app = app
    say("Controls at http://%s:%d/" % (arguments.host, arguments.port))
    if app.proposer is None:
        say("Compose is OFF. Restart with --llm stub, --llm local or --llm claude.")
    else:
        say("Compose is at /compose, backed by %r." % app.proposer.name)
        if not proposers.is_enabled():
            say("  ...but %s is not set, so it will refuse. Prefix the command "
                "with %s=1." % (proposers.ENABLE, proposers.ENABLE))
        say("  Drafts are filed in spec/drafts/ and are NOT counted as shipped controls.")

    server = SERVER((arguments.host, arguments.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
