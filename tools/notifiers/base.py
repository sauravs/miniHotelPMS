# -*- coding: utf-8 -*-
"""
THE TWO LOCKS THAT STOP A TEST SENDING AN EMAIL, AND WHERE A ROUTE COMES FROM.

Everything in this package lives OUTSIDE `hotelcontrols/` on purpose, exactly as
`tools/proposers/` does (D10). The engine holds a `Notifier` protocol and imports no backend;
`tools/serve.py` builds one and hands it in.

TWO LOCKS (brief §8.4)
----------------------
A live backend refuses to send unless `HOTELCONTROLS_NOTIFY=1` is set AND no test runner is
loaded in the process. An environment variable alone is a lock a test can open in one line, so
the test that sets it is refused anyway. Same names, same shape and the same test-runner list
as the transport's and the proposers' locks, so a grep for `HOTELCONTROLS_` finds every place
this repository decides to talk to something.

ROUTES: THE ENVIRONMENT, NO DEFAULT, NEVER COMMITTED
-----------------------------------------------------
`HOTELCONTROLS_NOTIFY_<AUDIENCE>` holds a comma-separated list of addresses. Staff addresses
are personal data, so they never appear in a committed file - not in a tenant config, not in a
fixture, not in a default here. An audience with no variable has no route, and the engine
leaves the task unsent saying so ("no route configured for audience finance").
"""
from __future__ import annotations

import os
import re
import sys

from hotelcontrols.actions import NotifyFailed

ENABLE = "HOTELCONTROLS_NOTIFY"
ROUTE_PREFIX = "HOTELCONTROLS_NOTIFY_"
TRUTHY = ("1", "true", "yes", "on")

# Same list the transport and the proposers use, and for the same reason.
TEST_RUNNERS = ("pytest", "_pytest", "unittest", "nose")


class NotifierDisabled(NotifyFailed):
    """A live backend was asked to send and is not armed.

    A `NotifyFailed`, so dispatch leaves the task unsent with this sentence as its note, rather
    than raising out of a run page. Being switched off is a fact about this process, and a task
    that says "email is off" is more useful than one that says nothing.
    """


def is_enabled() -> bool:
    """Lock 1: the environment variable. False unless explicitly truthy."""
    return os.environ.get(ENABLE, "").strip().lower() in TRUTHY


def under_test() -> bool:
    """Lock 2: whether a test runner is loaded. Read at call time, so an early import of this
    module cannot defeat it."""
    return any(name in sys.modules for name in TEST_RUNNERS)


def assert_armed(what: str) -> None:
    """Refuse unless both locks are open. Called before any connection is attempted."""
    if not is_enabled():
        raise NotifierDisabled(
            "%s is off. Set %s=1 to arm it. Email is opt-in: a control engine that mailed "
            "people by default would be one nobody could safely run a demo of." % (what, ENABLE))
    if under_test():
        raise NotifierDisabled(
            "%s refuses to arm inside a test process (%s is loaded). No test sends an email in "
            "this repository, and an environment variable alone would be a lock a test can open "
            "in one line - so this is the second one. Tests wire RecordingNotifier."
            % (what, ", ".join(name for name in TEST_RUNNERS if name in sys.modules)))


def route_variable(audience: str) -> str:
    """`front_office_manager` -> `HOTELCONTROLS_NOTIFY_FRONT_OFFICE_MANAGER`."""
    return ROUTE_PREFIX + re.sub(r"[^A-Za-z0-9]+", "_", audience).strip("_").upper()


def routes_from_environment(audience: str) -> tuple[str, ...]:
    """An audience's addresses from its variable, or () - never a default."""
    raw = os.environ.get(route_variable(audience), "")
    return tuple(address.strip() for address in raw.split(",") if address.strip())
