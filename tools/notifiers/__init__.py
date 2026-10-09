# -*- coding: utf-8 -*-
"""
EVERY BACKEND THAT CAN TELL SOMEBODY ABOUT A TASK, AND THE ONE LINE THAT PICKS ONE.

    build("off")    None - nothing is sent, and the queue page says email is not wired   <- default
    build("smtp")   one SMTP server, configured from the environment, behind two locks

`RecordingNotifier` is what tests wire; it is not offered to the launcher, because a demo that
showed "emailed to finance" for a message that never left the process would be telling a reader
something false.

THIS PACKAGE IS OUTSIDE THE ENGINE, AND THAT IS THE WHOLE DESIGN - the same shape as
`tools/proposers/` (D10). `hotelcontrols/` holds the `Notifier` protocol and imports nothing
from here; `tests/unit/test_notifiers_refuse_in_tests.py` asserts that over the AST.
"""
from __future__ import annotations

from hotelcontrols.actions import Notifier

from .base import (ENABLE, NotifierDisabled, assert_armed, is_enabled, route_variable,
                   routes_from_environment, under_test)
from .stub import RecordingNotifier

NAMES = ("off", "smtp")
DEFAULT = "off"


def build(name: str = DEFAULT) -> Notifier | None:
    """One backend by name, or None for "email is not wired"."""
    chosen = (name or DEFAULT).strip().lower()
    if chosen in ("off", "none", ""):
        return None
    if chosen == "smtp":
        from .smtp import SmtpNotifier
        return SmtpNotifier.from_environment()
    raise ValueError("no notifier called %r. Available: %s" % (name, ", ".join(NAMES)))


__all__ = ["DEFAULT", "ENABLE", "NAMES", "NotifierDisabled", "RecordingNotifier",
           "assert_armed", "build", "is_enabled", "route_variable", "routes_from_environment",
           "under_test"]
