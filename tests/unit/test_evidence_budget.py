# -*- coding: utf-8 -*-
"""
The call budget - the thing that stops a run.

R1: a folio takes one call per record and no bulk journal endpoint exists to replace it.
R8: the vendor asks integrators not to query wide date ranges without agreement. Together they
mean an unbounded control is an unbounded number of calls against someone else's server, and
the bound has to be enforced by code rather than by the population query having been written
carefully that day.

THE BUDGET RAISES. It does not truncate and it does not warn. A truncated population silently
answers a different question from the one asked - "no violations in the 40 records I happened to
look at" is indistinguishable, on screen, from "no violations".
"""
import pytest

from hotelcontrols.evidence import BudgetExceeded, CallBudget
from hotelcontrols.providers.base import Request


class TestSpending:
    def test_a_budget_counts_the_population_call_itself(self):
        """The first call is not free. A budget of 1 buys the population and nothing else."""
        budget = CallBudget(1)
        budget.spend(Request("GetReservationKey", {}))
        assert budget.remaining == 0

    def test_exceeding_the_budget_raises_before_the_call_is_made(self):
        """Spent BEFORE the call, so a run that would exceed it stops rather than making the
        call and apologising afterwards."""
        budget = CallBudget(1)
        budget.spend(Request("a", {}))
        with pytest.raises(BudgetExceeded):
            budget.spend(Request("b", {}))
        assert budget.spent == 1, "a refused call must not be counted as made"

    def test_the_message_says_what_to_do_about_it(self):
        """This reaches a screen. 'Narrow the window' is the action; 'raise the budget' is how
        a hotel ends up hammering its own PMS."""
        budget = CallBudget(1)
        budget.spend(Request("a", {}))
        with pytest.raises(BudgetExceeded) as caught:
            budget.spend(Request("b", {}))
        assert "narrow" in str(caught.value).lower()

    def test_a_budget_of_zero_is_refused_at_construction(self):
        with pytest.raises(ValueError):
            CallBudget(0)

    def test_it_reports_what_it_spent_so_a_test_can_assert_the_cost(self):
        budget = CallBudget(10)
        for _ in range(3):
            budget.spend(Request("x", {}))
        assert (budget.spent, budget.remaining) == (3, 7)
