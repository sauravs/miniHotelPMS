# -*- coding: utf-8 -*-
"""
Every guest's personal details in the 2026 captures, read through the adapters.

Shared by the tests that promise no guest PII leaves the engine in a message (slice 19's email)
or a log line (slice 20's operational log). Read through the providers rather than grepped from
the fixtures, so it is what the engine itself can see - on both wire formats - and so a new
capture is covered by existing.
"""
import re

from hotelcontrols.evidence.budget import CallBudget
from hotelcontrols.evidence.cache import ResponseCache
from hotelcontrols.evidence.population import population
from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers import registry as providers
from hotelcontrols.spec import TenantConfig, load

PROPERTIES = {"sandbox": "sandbox2026", "demo": "demo2026"}
GUEST_FIELDS = ("reservation.guest.given_name", "reservation.guest.surname",
                "reservation.guest.email", "reservation.guest.phone",
                "reservation.guest.id_number")


def collect() -> frozenset[str]:
    """Every guest name, email, phone and id number the 2026 captures hold."""
    found = set()
    for property_id, capture in PROPERTIES.items():
        tenant = TenantConfig.load(property_id)
        adapter, source = providers.load(tenant.provider).build(tenant, capture)
        records = population(load("required_reservation_fields"), adapter,
                             FixedClock.at(source.as_of, tenant.timezone),
                             ResponseCache(adapter.fetch, CallBudget(1000)))
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
