# -*- coding: utf-8 -*-
"""
THE DEMO, WITH THE COMPOSE FRONT END WIRED.

    python3 -m tools.serve --llm stub     fixed replies, nothing to install, no network
    python3 -m tools.serve --llm local    a model on this machine. FREE           <- default
    python3 -m tools.serve --llm claude   the hosted API. Paid, needs `anthropic`
    python3 -m tools.serve --llm off      identical to the plain server

    ... --store PATH                      keep the run history and the findings queue in a file
                                          (default: in memory, and the queue page says so)
    ... --notify smtp                     email each new task once to its audience (slice 19).
                                          Off by default, and behind HOTELCONTROLS_NOTIFY=1

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

from hotelcontrols.store import RunStore
from hotelcontrols.web.app import App
from hotelcontrols.web.server import HOST, PORT, SERVER, Handler

from . import notifiers, proposers

DRAFT_DIR = pathlib.Path(__file__).resolve().parents[1] / "spec" / "drafts"


def say(message: str) -> None:
    """Print, and flush. Stdout is block-buffered when it is a pipe rather than a terminal, so
    `python3 -m tools.serve > log &` showed an EMPTY log while the server ran perfectly - which
    hid the one line that says whether compose is armed."""
    print(message, flush=True)


def build_app(backend: str, draft_dir: pathlib.Path = DRAFT_DIR,
              store: str | None = None, notify: str = notifiers.DEFAULT,
              public_url: str | None = None) -> App:
    """The demo app, with a proposer if one was asked for, and a file store if one was.

    `store` is slice 18's opt-in `--store PATH`: without it the history and the findings queue
    are in memory, as they always were, and the queue page says they are lost on restart.
    `notify` is slice 19's: "off" unless asked, and a live backend still refuses to send until
    HOTELCONTROLS_NOTIFY=1 is set and no test runner is loaded.
    """
    proposer = proposers.build(backend)
    if proposer is not None:
        # Made here rather than on first write: a chat window that accepts a sentence and then
        # cannot file it has wasted the only expensive step in the flow.
        (draft_dir / "ir").mkdir(parents=True, exist_ok=True)
    extra = {"public_url": public_url} if public_url else {}
    return App(proposer=proposer, draft_dir=draft_dir if proposer is not None else None,
               store=RunStore(store) if store else None, notifier=notifiers.build(notify),
               **extra)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve the control engine demo, with the compose front end.")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--llm", default=proposers.DEFAULT, choices=proposers.NAMES,
                        help="which backend drafts a sentence (default: %(default)s)")
    parser.add_argument("--store", metavar="PATH", default=None,
                        help="keep the run history and the findings queue in this SQLite file "
                             "(default: in memory, lost on restart)")
    parser.add_argument("--notify", default=notifiers.DEFAULT, choices=notifiers.NAMES,
                        help="email each new task to its audience (default: %(default)s)")
    parser.add_argument("--public-url", default=None,
                        help="where an email's link points (default: http://HOST:PORT)")
    arguments = parser.parse_args(argv)

    try:
        app = build_app(arguments.llm, store=arguments.store, notify=arguments.notify,
                        public_url=arguments.public_url
                        or "http://%s:%d" % (arguments.host, arguments.port))
    except RuntimeError as exc:
        # A missing package or an unreachable host is a setup problem with a known fix, and the
        # backend itself already explains it. Printed and exited rather than raised, because a
        # traceback here says nothing a reader can act on.
        print("Could not start: %s" % exc, file=sys.stderr)
        return 2

    Handler.app = app
    say("Controls at http://%s:%d/" % (arguments.host, arguments.port))
    say("History and the findings queue are %s." % (
        "kept in %s" % arguments.store if arguments.store
        else "held in memory and lost on restart (--store PATH keeps them)"))
    if app.proposer is None:
        say("Compose is OFF. Restart with --llm stub, --llm local or --llm claude.")
    else:
        say("Compose is at /compose, backed by %r." % app.proposer.name)
        if not proposers.is_enabled():
            say("  ...but %s is not set, so it will refuse. Prefix the command "
                "with %s=1." % (proposers.ENABLE, proposers.ENABLE))
        say("  Drafts are filed in spec/drafts/ and are NOT counted as shipped controls.")
    if app.notifier is None:
        say("Email is OFF. Restart with --notify smtp to email each new task to its audience.")
    else:
        say("Email is wired (%s): each new task is emailed once to its audience." % app.notifier.name)
        if not notifiers.is_enabled():
            say("  ...but %s is not set, so it will refuse, and each task will say so."
                % notifiers.ENABLE)

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
