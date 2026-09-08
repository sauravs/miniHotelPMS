# -*- coding: utf-8 -*-
"""
RESPONSE CACHE - one response, one call, for the length of a run.

Review finding F19b. v1 cached follow-up responses PER RECORD, so a response fetched for record
A was fetched again for record B. That was harmless there only because the fields needing it
returned UNKNOWN before any call was made - but the moment references land (F1), the room master
is wanted by every one of 111 stays, and without a cache that is 111 calls for one answer, on
someone else's server (R8).

SCOPED TO A RUN, NEVER TO A PROCESS. Two runs an hour apart must not share evidence: every
control declares a freshness requirement, and a cache that outlived its run would quietly answer
today's question with yesterday's data.

FAILURES ARE CACHED TOO. A folio nobody captured must cost ONE attempt, not one per record that
happens to want it. Retrying a known failure once per record is the opposite of what R8 asks.
"""
from __future__ import annotations

from typing import Any, Callable

from ..providers.base import Request
from .budget import CallBudget


class ResponseCache:
    """Fetches each distinct request at most once, spending budget only on real calls."""

    __slots__ = ("_fetch", "_budget", "_responses", "_failures")

    def __init__(self, fetch: Callable[[Request], Any], budget: CallBudget) -> None:
        self._fetch = fetch
        self._budget = budget
        self._responses: dict[str, Any] = {}
        self._failures: dict[str, Exception] = {}

    def get(self, request: Request) -> Any:
        """The response for this request, fetching it if this run has not already.

        Re-raises a remembered failure rather than retrying: the second caller deserves the
        same answer as the first, and the provider deserves not to be asked twice.
        """
        key = request.key()
        if key in self._responses:
            return self._responses[key]
        if key in self._failures:
            raise self._failures[key]

        # Spent BEFORE the call, so a run that would exceed its budget stops rather than
        # making the call and apologising afterwards.
        self._budget.spend(request)
        try:
            response = self._fetch(request)
        except Exception as exc:
            self._failures[key] = exc
            raise
        self._responses[key] = response
        return response

    @property
    def calls(self) -> int:
        return len(self._responses) + len(self._failures)
