# -*- coding: utf-8 -*-
"""
REQUEST - what a guest asked for, structured, or refused at the door naming the field.

    parse_request(form) -> GuestRequest      or raises RequestRefused(field, message)

D12: the request is STRUCTURED. A reservation id and a time, HH:MM on the property's clock. No
model reads the guest's words on this path - "can I stay till 3?" misread as 13:00 or 03:00
prices a fee, and the decision would be confidently wrong about money (D10, applied to a
decision; `tests/unit/test_guest_no_model.py` proves nothing that could talk to a model is
reachable from this package).

The time is parsed EXACTLY as slice 21 parses a time parameter, by asking slice 21's own schema
to read it, so a request and a hotel's policy cannot disagree about what "15:00" means - and a
time written with an offset or a zone names a second clock and is refused, not converted (F11).

A refused request is not a decision. It is not stored and it raises no task: there is nothing to
decide about a request that did not say what it wanted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Mapping

from ..spec import ParameterSchema, SpecError

# One field, in slice 21's vocabulary, so the reader is slice 21's reader.
_TIME = ParameterSchema.from_dict(
    {"parameters": {"requested_time": {"type": "time_of_day", "required": True}}})


class RequestRefused(ValueError):
    """A malformed request, naming the field. The web layer answers it with a 400."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True, slots=True)
class GuestRequest:
    """A guest asks to check out late: which reservation, and until when."""

    reservation_id: str
    requested_time: time


def parse_request(form: Mapping[str, str]) -> GuestRequest:
    reservation_id = str(form.get("reservation_id") or "").strip()
    if not reservation_id:
        raise RequestRefused("reservation_id",
                             "reservation_id is required: the PMS's own reservation id")
    raw = form.get("requested_time")
    if raw is None or not str(raw).strip():
        raise RequestRefused("requested_time",
                             "requested_time is required, written HH:MM (24-hour) on the "
                             "property's own clock, e.g. 15:00")
    try:
        typed = _TIME.typed({"requested_time": str(raw).strip()}, tenant_id="this request",
                            currencies=())
    except SpecError as exc:
        # Slice 21 decided whether it reads; the words are this request's own, because its
        # refusal is addressed to a hotel's tenant file rather than to whoever sent a request.
        another = ("it names another clock (an offset or a zone), and a hotel's times are on "
                   "its own clock (F11); " if "another clock" in str(exc) else "")
        raise RequestRefused("requested_time",
                             "requested_time %r cannot be read: %swrite it HH:MM (24-hour) on "
                             "the property's own clock, e.g. 15:00" % (raw, another)) from None
    return GuestRequest(reservation_id, typed["requested_time"])
