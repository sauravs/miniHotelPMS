# -*- coding: utf-8 -*-
"""
THE PROBE PLAN - what would be asked, printed before anything is asked.

Decision D3: calls to the vendor sandbox are approved individually, bounded and staged. R8: the
vendor asks integrators not to query wide ranges without prior agreement, and the sandbox
belongs to them. Both need something concrete to approve, and "I will run the checkout control"
is not it.

So the gate for this slice is not "the probe works". It is:

    * `--plan` makes no calls at all, and says so;
    * the plan is STAGED - which calls are bulk and which grow with the population;
    * the plan is BOUNDED - every stage counted against the property's own budget;
    * `--run` refuses, here, always, because no test can arm the transport.

And one thing that is easy to get wrong and expensive to get wrong: a plan is made to be
pasted into a message to somebody. It renders placeholders where the credentials go, so the
first time it is useful is not the first time a password leaves the machine.
"""
import pytest

from hotelcontrols.spec import available, available_tenants
from tools import probe


def output(capsys, argv):
    code = probe.main(argv)
    return code, capsys.readouterr().out


class TestThePlanMakesNoCalls:

    def test_it_says_so_in_words(self, capsys):
        code, printed = output(capsys, ["--plan"])
        assert code == 0
        assert "No call was made" in printed

    def test_the_provider_source_is_never_fetched_from(self, capsys, monkeypatch):
        """Asserted rather than trusted. The plan builds an adapter to ask it structural
        questions - which endpoint, which key, which reference - and a plan that quietly
        fetched would be a probe running without approval, which is the one thing D3 exists to
        prevent."""
        from hotelcontrols.providers.minihotel.fixtures import FrozenSource

        def refuse(self, request):
            raise AssertionError("the plan fetched %s" % request.endpoint)

        monkeypatch.setattr(FrozenSource, "fetch", refuse)
        assert probe.main(["--plan", "--property", "sandbox"]) == 0

    @pytest.mark.parametrize("control_id", available())
    def test_every_control_has_a_plan(self, control_id, capsys):
        code, printed = output(capsys, ["--plan", "--property", "sandbox",
                                        "--control", control_id])
        assert code == 0
        assert control_id in printed
        assert "stage: population" in printed


class TestThePlanIsStagedAndBounded:

    def test_bulk_calls_and_per_record_calls_are_separate_stages(self, capsys):
        """The cost shape is the point. `1 + R + N`: the reference stage is O(1) however many
        records there are, and the per-record stage is the one that grows. An approver who
        cannot tell them apart cannot approve a window."""
        _code, printed = output(capsys, ["--plan", "--property", "sandbox",
                                         "--control", "checkout_money_owed"])
        assert "stage: population" in printed
        assert "stage: per record" in printed
        assert "one call PER RECORD" in printed

    def test_the_reference_stage_appears_where_a_control_joins(self, capsys):
        """Finding F1: the room master is one call per RUN, not one per record. That is the
        difference between three calls and a hundred and eleven."""
        _code, printed = output(capsys, ["--plan", "--property", "sandbox",
                                         "--control", "room_assignment_type_validity"])
        assert "stage: references" in printed
        assert "ONCE per run" in printed

    def test_every_plan_totals_its_calls_against_the_property_budget(self, capsys):
        _code, printed = output(capsys, ["--plan", "--property", "sandbox",
                                         "--control", "checkout_money_owed"])
        assert "BUDGET" in printed and "TOTAL" in printed

    def test_a_plan_over_the_budget_says_so_and_says_what_to_do(self, capsys):
        """"Narrow the window rather than raising the budget" is the same sentence the budget
        itself raises with (R1, R8). A plan that quietly totalled 400 calls would be a plan
        somebody approves by scrolling past it."""
        _code, printed = output(capsys, ["--plan", "--property", "sandbox",
                                         "--control", "checkout_money_owed",
                                         "--records", "500"])
        assert "OVER the property's budget" in printed
        assert "Narrow the window" in printed

    def test_the_window_is_resolved_through_the_property_clock(self, capsys):
        """F11 reaches the probe too. "Reservations that departed today" is a different set
        depending on whose midnight is being used, and a plan showing the machine's would be a
        plan for a different question."""
        _code, printed = output(capsys, ["--plan", "--property", "sandbox",
                                         "--control", "checkout_money_owed",
                                         "--as-of", "2026-07-08"])
        assert "2026-07-07" in printed and "2026-07-08" in printed
        assert "the property's own clock" in printed


class TestThePlanIsSafeToShowSomebody:

    def test_it_renders_placeholders_where_the_credentials_go(self, capsys, monkeypatch):
        """A plan is made to be pasted into a message. Its first useful outing must not also
        be a password's."""
        monkeypatch.setenv("HOTELCONTROLS_MINIHOTEL_PASSWORD", "hunter2")
        monkeypatch.setenv("HOTELCONTROLS_MINIHOTEL_USER", "real-account")
        _code, printed = output(capsys, ["--plan", "--property", "sandbox"])
        assert "hunter2" not in printed
        assert "real-account" not in printed
        assert "&lt;password&gt;" in printed

    def test_it_shows_the_actual_request_that_would_be_sent(self, capsys):
        """The thing being approved is the thing that happens. An approver reading "we would
        call GetReservationKey" is approving a name; one reading the body is approving a
        request."""
        _code, printed = output(capsys, ["--plan", "--property", "sandbox",
                                         "--control", "checkout_money_owed"])
        assert "POST" in printed
        assert "<GetReservationKey>" in printed
        assert '<BookingSearch Status="OUT" />' in printed

    def test_a_provider_nobody_has_ever_called_says_it_cannot_be_probed(self, capsys):
        """DemoPMS is fictional. Printing a plausible request for it would make the transport
        look more finished than it is."""
        _code, printed = output(capsys, ["--plan", "--property", "demo"])
        assert "no live request form" in printed
        assert "replayed, not probed" in printed


class TestRunRefuses:

    def test_run_without_yes_refuses_and_names_the_decision(self, capsys):
        code, printed = output(capsys, ["--run", "--property", "sandbox",
                                        "--control", "checkout_money_owed"])
        assert code == 2
        assert "--yes" in printed and "D3" in printed

    def test_run_with_yes_still_refuses_because_the_transport_cannot_arm_here(
            self, capsys, monkeypatch):
        """The whole slice in one assertion. The environment variable is set, `--yes` is given,
        and it is still refused - because a test runner is loaded and criterion 11 says no test
        can reach the network."""
        monkeypatch.setenv("HOTELCONTROLS_LIVE", "1")
        for name in ("USER", "PASSWORD", "HOTEL", "BASE_URL"):
            monkeypatch.setenv("HOTELCONTROLS_MINIHOTEL_%s" % name, "x")

        code, printed = output(capsys, ["--run", "--yes", "--property", "sandbox",
                                        "--control", "checkout_money_owed"])
        assert code == 2
        assert "REFUSED" in printed
        assert "test process" in printed

    def test_a_missing_credential_is_a_different_refusal_from_a_disabled_transport(
            self, capsys, monkeypatch):
        """Three refusals, each saying which one it is. One message for "you did not confirm",
        "the transport is off" and "there is no password" would send an operator looking in the
        wrong place two times out of three."""
        monkeypatch.delenv("HOTELCONTROLS_LIVE", raising=False)
        code, printed = output(capsys, ["--run", "--yes", "--property", "sandbox"])
        assert code == 2
        assert "HOTELCONTROLS_LIVE" in printed


class TestTheCommandLineItself:

    def test_an_unknown_property_is_refused_naming_the_ones_that_exist(self, capsys):
        code, printed = output(capsys, ["--plan", "--property", "nowhere"])
        assert code == 2
        for tenant_id in available_tenants():
            assert tenant_id in printed

    def test_an_unknown_control_is_refused_naming_the_ones_that_exist(self, capsys):
        code, printed = output(capsys, ["--plan", "--control", "no_such_control"])
        assert code == 2
        assert "checkout_money_owed" in printed

    def test_with_no_arguments_it_plans_rather_than_calls(self, capsys):
        """The default is the safe one. A tool whose bare invocation made calls would be a tool
        somebody runs once by accident."""
        code, printed = output(capsys, [])
        assert code == 0
        assert "PLAN ONLY" in printed
