# -*- coding: utf-8 -*-
"""
The run-scoped response cache.

Review finding F19b. v1 cached follow-up responses PER RECORD, so a response fetched for record
A was fetched again for record B. It was harmless there only because such fields returned
UNKNOWN before a call was ever made - but the moment references land (F1), the room master is
wanted by every one of 111 stays, and without a cache that is 111 calls for one answer.

The cache is scoped to a RUN, never to a process. Two runs an hour apart must not share
evidence: a control declares a freshness requirement, and a cache that outlived the run would
quietly answer today's question with yesterday's data.
"""
import pytest

from hotelcontrols.evidence import CallBudget, ResponseCache
from hotelcontrols.providers.base import Request


class Counting:
    """A source that records how often it was actually asked."""

    def __init__(self):
        self.calls = []

    def fetch(self, request):
        self.calls.append(request)
        return "<Response id='%d' />" % len(self.calls)


class TestItFetchesOnce:
    def test_the_same_request_is_fetched_once_however_often_it_is_asked_for(self):
        source, budget = Counting(), CallBudget(10)
        cache = ResponseCache(source.fetch, budget)
        request = Request("getRooms", {})
        first = cache.get(request)
        for _ in range(10):
            assert cache.get(request) is first
        assert len(source.calls) == 1

    def test_a_cached_response_costs_no_budget(self):
        """The point of the cache, stated as a number: 111 stays wanting the room master cost
        one call, not 111."""
        source, budget = Counting(), CallBudget(3)
        cache = ResponseCache(source.fetch, budget)
        for _ in range(50):
            cache.get(Request("getRooms", {}))
        assert budget.spent == 1

    def test_requests_differing_only_in_key_order_share_an_entry(self):
        source, budget = Counting(), CallBudget(10)
        cache = ResponseCache(source.fetch, budget)
        cache.get(Request("X", {"a": 1, "b": 2}))
        cache.get(Request("X", {"b": 2, "a": 1}))
        assert len(source.calls) == 1

    def test_different_requests_are_different_entries(self):
        source, budget = Counting(), CallBudget(10)
        cache = ResponseCache(source.fetch, budget)
        cache.get(Request("GetReservationBalance", {"ReservationNumber": "1"}))
        cache.get(Request("GetReservationBalance", {"ReservationNumber": "2"}))
        assert len(source.calls) == 2


class TestFailuresAreRemembered:
    def test_a_failed_fetch_is_not_retried_for_every_record(self):
        """A folio nobody captured must cost ONE attempt, not one per record that wants it.
        Retrying a known failure against someone else's server is the opposite of R8."""
        class Failing:
            calls = []

            def fetch(self, request):
                self.calls.append(request)
                raise LookupError("not captured")

        source = Failing()
        cache = ResponseCache(source.fetch, CallBudget(10))
        request = Request("GetReservationBalance", {"ReservationNumber": "007004365"})
        for _ in range(5):
            with pytest.raises(LookupError):
                cache.get(request)
        assert len(source.calls) == 1

    def test_the_same_failure_is_re_raised_rather_than_becoming_a_success(self):
        class Failing:
            def fetch(self, request):
                raise LookupError("not captured")

        cache = ResponseCache(Failing().fetch, CallBudget(10))
        request = Request("x", {})
        with pytest.raises(LookupError):
            cache.get(request)
        with pytest.raises(LookupError) as second:
            cache.get(request)
        assert "not captured" in str(second.value)


class TestBudgetInteraction:
    def test_the_budget_is_spent_before_the_call(self):
        source = Counting()
        budget = CallBudget(1)
        cache = ResponseCache(source.fetch, budget)
        cache.get(Request("a", {}))
        from hotelcontrols.evidence import BudgetExceeded
        with pytest.raises(BudgetExceeded):
            cache.get(Request("b", {}))
        assert len(source.calls) == 1, "the refused call must never reach the source"
