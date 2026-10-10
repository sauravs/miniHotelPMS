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


# --------------------------------------------------------------------------- issue #70
# `--run` used to send each control's POPULATION call and nothing else, while `--plan` printed
# the references and the per-record calls too. So the command docs/open-questions.md 1.2 gave
# for `getRooms` and `getRoomTypes` would have sent a 90-day reservation query instead, which
# nobody approved, and neither of the two calls 1.2 needs. D3 makes the printed plan the
# approval, so everything below compares what would be SENT with what was PRINTED.

def printed_requests(printed):
    """(endpoint, filters) for every request a printed plan names, in printed order."""
    lines = printed.splitlines()
    return [(line.split("endpoint ", 1)[1], lines[number + 1].split("filters  ", 1)[1])
            for number, line in enumerate(lines) if line.startswith("   endpoint ")]


def distinct(pairs):
    seen = []
    for pair in pairs:
        if pair not in seen:
            seen.append(pair)
    return seen


def sent_to_frozen_source(argv):
    """What `--run` would send for these arguments - sent to the FROZEN source, which records
    every request it is asked and has no network to reach."""
    prepared = probe.prepare(argv)
    requests = probe.sendable(prepared.sections, prepared.package.encoder)
    adapter, source = prepared.package.build(prepared.tenant)
    probe.send(requests, adapter)
    return [(request.endpoint, str(request.params or "(none)")) for request in source.calls]


class TestRunSendsWhatThePlanPrinted:

    @pytest.mark.parametrize("argv", [
        ["--control", "resource_occupancy_consistency"],
        ["--control", "room_assignment_type_validity", "--endpoint", "getRoomTypes"],
        ["--control", "room_assignment_type_validity", "--endpoint", "getRooms"],
        # Population AND both references: the stages the old `--run` printed and never sent.
        ["--control", "room_assignment_type_validity"],
        # Two controls sharing a reference: `getRooms` is printed twice and sent once.
        ["--control", "room_assignment_type_validity", "--control", "room_capacity_compliance"],
        ["--reask", "9_departures_2026-07.xml", "--with", "IncludeRoomPrices"],
    ])
    def test_the_distinct_requests_printed_are_exactly_the_requests_sent(self, argv, capsys):
        """D3, issue #70. The thing being approved is the thing that happens: no call missing,
        no call added, none sent twice."""
        argv = ["--property", "sandbox"] + argv
        _code, printed = output(capsys, ["--plan"] + argv)
        sent = sent_to_frozen_source(argv)
        capsys.readouterr()
        assert sent == distinct(printed_requests(printed))
        assert sent, "a comparison of two empty lists would pass vacuously"

    def test_a_per_record_stage_is_refused_rather_than_skipped(self):
        """Issue #70. A per-record call is printed with a placeholder record id, so it cannot be
        sent as printed. Skipping it quietly is how the old `--run` came to send a different
        set of calls from the one approved."""
        prepared = probe.prepare(["--property", "sandbox", "--control", "checkout_money_owed"])
        with pytest.raises(probe.Refused, match="--endpoint"):
            probe.sendable(prepared.sections, prepared.package.encoder)

    def test_narrowed_to_its_population_the_same_control_can_be_sent(self):
        prepared = probe.prepare(["--property", "sandbox", "--control", "checkout_money_owed",
                                  "--endpoint", "GetReservationKey"])
        requests = probe.sendable(prepared.sections, prepared.package.encoder)
        assert [request.endpoint for request in requests] == ["GetReservationKey"]

    def test_a_plan_holding_a_request_the_encoder_refuses_sends_nothing_at_all(self):
        """R8. `ooo_room_protection` joins occupancy with NO window, which the live form refuses
        as the wide query the vendor asked us not to send. Sending the rest would be a
        different plan from the one printed, so none of it is sent."""
        prepared = probe.prepare(["--property", "sandbox", "--control", "ooo_room_protection"])
        with pytest.raises(probe.Refused, match="RoomStatusInquiry"):
            probe.sendable(prepared.sections, prepared.package.encoder)

    def test_run_through_main_sends_what_it_printed_once_each_and_dates_the_recording(
            self, capsys, monkeypatch):
        """The whole `--run` path, issue #70. The arm lock is replaced here, and so is the only
        thing it guards: the live source becomes a fake that has no dialer and records what it
        is asked. Every other step - selection, refusal, recorder, attempts - is the real one.

        Two things only this path can show. Each approved request goes out ONCE: the transport
        retries a transient failure, and a retry is a second call nobody approved, so a probe
        asks for one attempt. And the recording is dated the day the call is MADE, by the
        property's clock - not the day the plan is resolved against (F7: as_of and observed_at
        are different facts)."""
        made = {}

        class FakeLive:
            def __init__(self, provider, encoder, credentials, clock, recorder=None,
                         attempts=None, **_):
                made.update(recorder=recorder, attempts=attempts, sent=[])
                self.encoder, self.credentials = encoder, credentials

            def fetch(self, request):
                self.encoder(request, self.credentials)   # the real form, never dialled
                made["sent"].append((request.endpoint, str(request.params or "(none)")))
                return "<Response />"

        from hotelcontrols.kernel import FixedClock
        monkeypatch.setattr(probe, "assert_armed", lambda: None)
        monkeypatch.setattr(probe.Credentials, "from_environment",
                            classmethod(lambda cls, provider: probe.PLACEHOLDER))
        monkeypatch.setattr(probe, "LiveSource", FakeLive)
        monkeypatch.setattr(probe, "PropertyClock",
                            lambda zone: FixedClock.at("2026-10-10T11:00", zone))

        argv = ["--property", "sandbox", "--control", "room_assignment_type_validity"]
        _code, printed = output(capsys, ["--plan"] + argv)
        code, _ran = output(capsys, ["--run", "--yes"] + argv)

        assert code == 0
        assert made["sent"] == distinct(printed_requests(printed))
        assert made["attempts"] == 1
        assert made["recorder"].observed_at == "2026-10-10"
        assert made["recorder"].as_of == "2026-07-08"
        assert made["recorder"].capture == "probe-2026-10-10"


class TestOnePrintedRequestAtATime:

    def test_endpoint_narrows_a_plan_to_that_one_request(self, capsys):
        """D3 approves CALLS, and a control's plan can hold three. `getRoomTypes` is nobody's
        population, so before #70 it could be printed and never sent."""
        code, printed = output(capsys, ["--plan", "--property", "sandbox",
                                        "--control", "room_assignment_type_validity",
                                        "--endpoint", "getRoomTypes"])
        assert code == 0
        assert printed_requests(printed) == [("getRoomTypes", "(none)")]
        assert "TOTAL     1 call(s)" in printed

    def test_an_endpoint_the_plan_does_not_hold_is_refused_naming_the_ones_it_does(
            self, capsys):
        code, printed = output(capsys, ["--plan", "--property", "sandbox",
                                        "--control", "resource_occupancy_consistency",
                                        "--endpoint", "getRoomTypes"])
        assert code == 2
        assert "RoomStatusInquiry" in printed


class TestReaskingARecordedQuestion:

    def test_reask_prints_the_recorded_question_verbatim(self, capsys):
        """Slice 23 refreshes evidence by asking again what was asked before, so the old and
        new captures answer the SAME question and can be compared (F19c: a capture is only as
        good as the request recorded beside it)."""
        code, printed = output(capsys, ["--plan", "--property", "sandbox",
                                        "--reask", "9_departures_2026-07.xml"])
        assert code == 0
        assert printed_requests(printed) == [
            ("GetReservationKey", str({"DepartureDate": {"From": "2026-07-01",
                                                         "To": "2026-08-09"}}))]
        assert '<DepartureDate From="2026-07-01" To="2026-08-09" />' in printed
        assert "TOTAL     1 call(s)" in printed

    def test_with_room_prices_adds_that_flag_and_nothing_else(self, capsys):
        """#49: `stay.rate_code` is absent from every reservation capture, because none was
        taken with room prices. The re-asked window is unchanged; only the flag is added."""
        code, printed = output(capsys, ["--plan", "--property", "sandbox",
                                        "--reask", "9_departures_2026-07.xml",
                                        "--with", "IncludeRoomPrices"])
        assert code == 0
        assert printed_requests(printed) == [
            ("GetReservationKey", str({"DepartureDate": {"From": "2026-07-01",
                                                         "To": "2026-08-09"},
                                       "IncludeRoomPrices": True}))]
        assert "<IncludeRoomPrices>true</IncludeRoomPrices>" in printed

    def test_with_refuses_an_option_that_is_not_on_its_list(self, capsys):
        """An added option can change which records come back, not only what each one carries.
        So the list is explicit, and widening it is a decision rather than a flag (R1, R8)."""
        code, printed = output(capsys, ["--plan", "--property", "sandbox",
                                        "--reask", "9_departures_2026-07.xml",
                                        "--with", "Cancellations"])
        assert code == 2
        assert "IncludeRoomPrices" in printed

    def test_with_never_overwrites_what_the_recorded_question_already_asked(self, capsys):
        code, _printed = output(capsys, ["--plan", "--property", "sandbox",
                                         "--reask", "3_GetReservationKey.xml",
                                         "--with", "IncludeRoomPrices"])
        assert code == 2

    def test_with_needs_a_recorded_question_to_add_to(self, capsys):
        code, printed = output(capsys, ["--plan", "--property", "sandbox",
                                        "--control", "required_reservation_fields",
                                        "--with", "IncludeRoomPrices"])
        assert code == 2
        assert "--reask" in printed

    def test_reask_and_control_together_are_refused(self, capsys):
        """One or the other. A plan made of both would be approved as one thing and be two."""
        code, _printed = output(capsys, ["--plan", "--property", "sandbox",
                                         "--reask", "9_departures_2026-07.xml",
                                         "--control", "checkout_money_owed"])
        assert code == 2

    def test_reask_of_a_file_nobody_recorded_is_refused_naming_the_ones_that_were(
            self, capsys):
        code, printed = output(capsys, ["--plan", "--property", "sandbox",
                                        "--reask", "99_never_captured.xml"])
        assert code == 2
        assert "9_departures_2026-07.xml" in printed
