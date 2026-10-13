# -*- coding: utf-8 -*-
"""
Every guest's personal details in the 2026 captures, read through the adapters.

Read from the COVERING captures (issue #71), and from every reservation question each one
recorded - departures, arrivals and creations - so the 385 + 150 guests the covering calls
brought in are probed too, not only the departure window sandbox2026 holds.

Shared by the tests that promise no guest PII leaves the engine in a message (slice 19's email)
or a log line (slice 20's operational log). Read through the providers rather than grepped from
the fixtures, so it is what the engine itself can see - on both wire formats - and so a new
capture is covered by existing.
"""
import re

from hotelcontrols.providers import registry as providers
from hotelcontrols.providers.base import Request
from hotelcontrols.spec import TenantConfig

PROPERTIES = {"sandbox": "sandbox2026cover", "demo": "demo2026cover"}
# Each provider's reservation endpoint, as the capture index names it.
RESERVATIONS = {"sandbox": "GetReservationKey", "demo": "bookings"}
GUEST_FIELDS = ("reservation.guest.given_name", "reservation.guest.surname",
                "reservation.guest.email", "reservation.guest.phone",
                "reservation.guest.id_number")


def collect() -> frozenset[str]:
    """Every guest name, email, phone and id number the 2026 captures hold."""
    found = set()
    for property_id, capture in PROPERTIES.items():
        tenant = TenantConfig.load(property_id)
        adapter, source = providers.load(tenant.provider).build(tenant, capture)
        questions = [r["request"] for r in source.index["responses"]
                     if r["endpoint"] == RESERVATIONS[property_id]
                     and capture in r.get("captures", [])]
        assert len(questions) == 3, "departures, arrivals and creations"
        records = [record for question in questions
                   for record in adapter.records(
                       adapter.fetch(Request(RESERVATIONS[property_id], question)),
                       "reservation")]
        for record in records:
            for field in GUEST_FIELDS:
                value = adapter.resolve(field, record)
                if value.is_known and isinstance(value.payload, str) and value.payload.strip():
                    found.add(value.payload.strip())
    # Measured, not assumed: the captures hold phone "numbers" of two and three digits (`04`,
    # `08`, `265`) and a four-digit id. A value that short cannot be told apart from the day in
    # `2026-07-08` or a digit of an amount, so purely numeric values under five digits are left
    # out - they identify nobody. Every name, every email and every longer number stays in.
    found = {d for d in found if not (d.isdigit() and len(d) < 5)}
    assert len(found) > 50, "the PII probe found almost nothing - it would pass vacuously"
    return frozenset(found)


def leaks(text: str, details) -> list[str]:
    """The guest details that appear in `text` as whole words, plus a card token if one does."""
    return sorted(d for d in details if re.search(r"(?<!\w)%s(?!\w)" % re.escape(d), text)) \
        + (["****"] if "****" in text else [])
