# -*- coding: utf-8 -*-
"""
POPULATION - the bounded set of records a control will look at.

`control_rule_architecture.docx` section 24 is where this comes from:

    Don't evaluate every control against every reservation. The compiler should generate a
    population query. ... This is important for scale and API cost.

It is also the only defence against R1. A folio costs one call per record and no bulk journal
endpoint exists, so "every reservation" is not a set this engine can afford to look at.

WHAT THIS LAYER RESOLVES, AND WHAT IT LEAVES ALONE
--------------------------------------------------
The IR carries the query as opaque per-provider data. The only thing touched here is a RELATIVE
DATE - `today`, `today-1d`, `today+90d` - and it is resolved through the PROPERTY'S clock, never
the machine's (F11). At 22:30 UTC it is already tomorrow in Jerusalem, so "who checked out
today" has a different answer depending on which clock is asked, and the hotel's is the only one
that is correct.

An unrecognised relative-date token RAISES. Passing it through would send a token we do not
understand to somebody else's parser, and the population would be silently wrong rather than
obviously empty.
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from ..kernel import Clock
from ..providers.base import Request

_RELATIVE_DATE = re.compile(r"^today(?:([+-])(\d+)d)?$")


def build_request(ir, provider_name: str, clock: Clock) -> Request:
    """The IR's population query for one provider, with its relative dates resolved.

    Endpoint and filters are the provider's own vocabulary, carried as data in the IR. This
    layer resolves the dates and changes nothing else - it could not, because it does not know
    what any of the other keys mean.
    """
    queries = ir["population"]["provider_query"]
    if provider_name not in queries:
        raise KeyError("%s declares no population query for provider %r"
                       % (ir.get("control_id", "this control"), provider_name))
    query = queries[provider_name]
    return Request(query["endpoint"], _resolve_dates(query.get("filters", {}), clock))


def _resolve_dates(value: Any, clock: Clock) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_dates(item, clock) for key, item in value.items()}
    if isinstance(value, str) and value.startswith("today"):
        match = _RELATIVE_DATE.match(value)
        if not match:
            raise ValueError(
                "unrecognised relative date %r in a population query - passing a token we do "
                "not understand to the provider would make the population silently wrong "
                "rather than obviously empty" % (value,))
        sign, days = match.groups()
        offset = timedelta(days=int(days or 0) * (-1 if sign == "-" else 1))
        return (clock.today() + offset).strftime("%Y-%m-%d")
    return value


def population(ir, adapter, clock: Clock, cache) -> list:
    """Every record the control's bounded query returns, uncut and unfiltered.

    Deliberately NOT filtered here. The population query is a bound, not a verdict: deciding
    that a record is out of scope is the evaluator's rule, and applying it here as well would
    mean the scope clause could never be exercised against real data. (The provider does return
    records nobody asked for - two cancelled bookings arrived in a probe that never requested
    cancellations - so scope filtering has to happen; it just happens one layer up.)
    """
    response = cache.get(build_request(ir, adapter.name, clock))
    return adapter.records(response, ir["entity"])
