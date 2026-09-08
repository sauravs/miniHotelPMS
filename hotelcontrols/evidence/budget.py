# -*- coding: utf-8 -*-
"""
CALL BUDGET - the thing that stops a run.

R1: a folio takes one call per record and no bulk journal endpoint exists to replace it.
R8: the vendor asks integrators not to query wide date ranges without agreement.

Together they mean an unbounded control is an unbounded number of calls against someone else's
server, and the bound has to be enforced by CODE rather than by the population query having been
written carefully on the day.

THE BUDGET RAISES. It does not truncate, and it does not warn. A truncated population silently
answers a different question from the one the control asked - and "no violations in the forty
records I happened to look at" is indistinguishable, on screen, from "no violations".

(Which endpoint is which is the provider adapter's business. This layer only counts.)
"""
from __future__ import annotations

from ..providers.base import Request


class BudgetExceeded(RuntimeError):
    """The run would have cost more calls than it was allowed. Nothing further is fetched."""


class CallBudget:
    """How many provider calls one run may make, including the population call itself."""

    __slots__ = ("limit", "spent", "requests")

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("a run needs at least one call to fetch its population")
        self.limit = limit
        self.spent = 0
        # Kept so a test can assert WHAT was called and not merely how often - the difference
        # between "three calls" and "the three calls we expected".
        self.requests: list[Request] = []

    def spend(self, request: Request) -> int:
        if self.spent + 1 > self.limit:
            raise BudgetExceeded(
                "this run is limited to %d provider calls and has already made %d; refusing to "
                "fetch %s. Narrow the population window rather than raising the budget "
                "(R1, R8)" % (self.limit, self.spent, request.endpoint))
        self.spent += 1
        self.requests.append(request)
        return self.spent

    @property
    def remaining(self) -> int:
        return self.limit - self.spent

    def __repr__(self) -> str:
        return "CallBudget(%d/%d spent)" % (self.spent, self.limit)
