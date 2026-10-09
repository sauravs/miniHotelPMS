# -*- coding: utf-8 -*-
"""
THE OPERATIONAL LOG - what ran, for whom, how long it took and what it cost.

    OpsLog(clock, logger).emit(event, **fields) -> dict      one JSON line per boundary

Slice 20 (G14, narrowed). Structured records through the standard `logging` module, at three
boundaries the layer above the run owns: the web REQUEST, the RUN, and action DISPATCH. Every
record carries the same five keys - `tenant_id`, `run_id`, `control_id`, `policy_version`,
`provider` - null where a boundary has none, so one `run_id` can be followed from the request
that asked for it, through the run, to the email it caused.

THE TIMESTAMP IS OURS, NOT THE LOGRECORD'S
-------------------------------------------
A `LogRecord` reads the machine's wall clock the moment it is made, and `kernel/clock.py` is
the only module in the engine allowed to read one (F11, asserted over the AST). So the line
written is the record built here, stamped by an INJECTED clock, and the formatter below writes
that and nothing else - no `asctime`, no `created`, no level name. A test that pins the clock
gets the same timestamp on every line; a running service gets the kernel's own clock, in UTC,
because an operational log is about the service and not about one hotel's calendar.

WHAT NEVER GOES IN
------------------
Guest details, credentials, staff addresses, and anything a provider said. That is a property
of what the callers pass rather than of a filter here: the request line carries the PATH with
no query string, a run line carries counts and coverage and whether it was blocked - not the
blocked reason, which is a provider's own words - and a dispatch line carries the audience and
the outcome, never the note or the addresses. Nothing is logged from inside `providers/` or
`evaluator/`, and a test fails if either imports logging.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from ..kernel import Clock, PropertyClock

LOGGER_NAME = "hotelcontrols.ops"

# The five keys every record carries, in this order, null where a boundary has none.
CARRIES = ("tenant_id", "run_id", "control_id", "policy_version", "provider")


class OpsLog:
    """Emits operational records through a logger, each stamped by an injected clock."""

    def __init__(self, clock: Clock | None = None, logger: logging.Logger | None = None):
        # The production default is the kernel's clock in UTC. A test hands in a FixedClock.
        self.clock = clock if clock is not None else PropertyClock("UTC")
        self.logger = logger if logger is not None else logging.getLogger(LOGGER_NAME)

    def now(self) -> datetime:
        return self.clock.now()

    def emit(self, event: str, **fields) -> dict:
        """Build one record, hand it to the logger, and return it."""
        record = {"at": self.now().isoformat(), "event": event}
        record.update({key: fields.pop(key, None) for key in CARRIES})
        record.update(fields)
        self.logger.info(event, extra={"ops": record})
        return record


def elapsed_ms(started: datetime, finished: datetime) -> int:
    """Whole milliseconds between two instants of the injected clock, rounded half up.

    Integer arithmetic on the timedelta rather than floating seconds, so 1.2345 s is 1235 ms
    on every platform rather than whichever way a float happens to round.
    """
    delta: timedelta = finished - started
    micro = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
    return (micro + 500) // 1000


class JsonLines(logging.Formatter):
    """One record, one line of JSON: exactly what `OpsLog` built, and nothing of the LogRecord.

    A record that did not come from `OpsLog` - something else logging to this logger - is
    written as its message alone, so even then no wall-clock reading reaches a line.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "ops", None)
        if payload is None:
            payload = {"event": record.getMessage()}
        return json.dumps(payload, ensure_ascii=False, default=str)


def attach(stream) -> logging.Handler:
    """Write the operational log to `stream`, as JSON lines. What the server's `--log` does.

    The ops logger stops propagating once attached, so its lines are not duplicated into
    whatever handlers an embedding application has put on the root logger.
    """
    logger = logging.getLogger(LOGGER_NAME)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLines())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return handler
