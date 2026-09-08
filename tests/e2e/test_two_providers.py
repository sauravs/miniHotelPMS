# -*- coding: utf-8 -*-
"""
SUCCESS CRITERION 7 - the same IR, over the same logical hotel, through two providers, yielding
the same verdicts.

This is the file the whole architecture is for. Every layer above `providers/` exists in the
shape it does so that this test can pass without any of them changing, and the eight-layer
diagram in `architecture.md` is worth exactly what this file is worth.

WHAT "THE SAME HOTEL" MEANS HERE
--------------------------------
Not two hand-written fixture sets that happen to agree. `fixtures/demopms/` is the MiniHotel
captures re-encoded field by field by `tools/transcode_demopms.py` - the same 138 reservations,
the same 28 rooms, the same five folios, the same two occupancy segments, and the same evidence
GAPS. The folios that were never captured are still missing. The statuses nobody can name are
still unnameable. The 23 rooms with no configured capacity are still unconfigured.

That last part is what makes this a test rather than a demonstration. A demo hotel that knew
more than the captured one would make this criterion pass by being a different hotel.

WHAT IS ALLOWED TO DIFFER
--------------------------
The REASON, and only the reason. "0 means unconfigured in this provider" and "this provider
writes -1 where a value was never configured" are different sentences about the same gap, and
both are correct about their own wire format. What may never differ is the outcome, the record
it is about, or whether the run concluded anything at all.

The wire formats were chosen to disagree as much as possible: three numeric date formats
against one carrying a month name, an overloaded 0 against an out-of-band sentinel, a currency
kept away from its amount against one kept with it, sibling occupancy against nested occupancy,
"YES" against true. If those can produce identical verdicts, the boundary is real.
"""
from collections import Counter

import pytest

from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers.base import ResponseUnavailable
from hotelcontrols.providers.registry import all_providers
from hotelcontrols.runner import run
from hotelcontrols.spec import TenantConfig, available

# The two properties are the same hotel. One runs the real PMS, the other the fictional one,
# and each names its provider in its own tenant file - so this pairing is read from `spec/`
# rather than asserted here, and a third provider joins by adding a tenant.
PROPERTIES = ("sandbox", "demo")

# Three instants, chosen so that between them every control is exercised in a state that
# matters: answering, excluding everything, reaching only unknowns, and refused outright.
#
#   2026-07-08  the week the checkout controls were built for
#   2024-09-01  the older body of evidence, where most windows are not covered
#   2024-08-14  the one week the occupancy capture can answer (issue #9)
INSTANTS = ("2026-07-08T09:00", "2024-09-01T09:00", "2024-08-14T09:00")

# Which capture each property was asked about, per instant. The 2026 captures answer 2026
# questions and the 2024 ones answer 2024 questions; asking the other way round is refused, and
# that refusal is itself asserted below.
CAPTURES = {
    "2026-07-08T09:00": {"sandbox": "sandbox2026", "demo": "demo2026"},
    "2024-09-01T09:00": {"sandbox": "sandbox2024", "demo": "demo2024"},
    "2024-08-14T09:00": {"sandbox": "sandbox2024", "demo": "demo2024"},
}


def a_run(property_id, control_id, as_of):
    """One control, one property, one instant - through whichever provider that property runs.

    Note what this function does NOT do: choose an adapter, know a wire format, or branch on
    which PMS answered. It reads the property's tenant file, asks the registry for the provider
    that file names, and runs. That is the whole claim, in eight lines.
    """
    tenant = TenantConfig.load(property_id)
    package = next(p for p in all_providers() if p.name == tenant.provider)
    adapter, source = package.build(tenant, CAPTURES[as_of][property_id])
    result = run(control_id, tenant, adapter, FixedClock.at(as_of, tenant.timezone),
                 evidence_label=CAPTURES[as_of][property_id])
    return result, source


def outcomes(result):
    """A run reduced to what criterion 7 is about: which record got which answer.

    A Counter of pairs rather than a set, because one reservation can appear as several
    occupancy segments and two of its segments getting different answers is a real difference
    that a set would hide.
    """
    if result.is_blocked:
        return "blocked"
    return Counter((v.record_id, v.outcome.value) for v in result.verdicts)


@pytest.mark.parametrize("as_of", INSTANTS)
@pytest.mark.parametrize("control_id", sorted(available()))
class TestTheSameIrThroughTwoProviders:
    """The criterion, control by control and instant by instant."""

    def test_every_record_gets_the_same_answer_from_both_providers(self, control_id, as_of):
        first, second = (a_run(p, control_id, as_of)[0] for p in PROPERTIES)
        assert outcomes(first) == outcomes(second), (
            "%s at %s disagrees between providers.\n  %s: %s\n  %s: %s"
            % (control_id, as_of, first.provider, outcomes(first),
               second.provider, outcomes(second)))

    def test_a_control_blocked_on_one_provider_is_blocked_on_the_other(self, control_id, as_of):
        """The unglamorous half, and the easier one to get wrong. If one provider's evidence
        could answer a question the other's could not, every agreement above would be an
        agreement about a smaller set of questions."""
        blocked = [a_run(p, control_id, as_of)[0].is_blocked for p in PROPERTIES]
        assert len(set(blocked)) == 1, (
            "%s at %s is blocked on one provider and not the other" % (control_id, as_of))

    def test_both_cost_the_same_number_of_calls(self, control_id, as_of):
        """R1, and a stronger claim than it looks. The cost model is `1 + R + N` and it is a
        property of the CONTROL - its population bound, its references, its per-record
        follow-ups - not of the API underneath. A provider needing a call more would mean the
        IR's cost declaration was really a statement about one vendor."""
        calls = [a_run(p, control_id, as_of)[0].calls for p in PROPERTIES]
        assert len(set(calls)) == 1, (
            "%s at %s costs %s calls depending on the provider" % (control_id, as_of, calls))


class TestTheAgreementIsNotVacuous:
    """Guards. Two providers that both answer nothing agree perfectly and prove nothing."""

    def test_the_providers_reach_real_conclusions_to_agree_about(self):
        for property_id in PROPERTIES:
            concluded = [c for c in available()
                         if a_run(property_id, c, "2026-07-08T09:00")[0].coverage.concluded]
            assert len(concluded) == 5, (
                "%s reaches %d conclusions - update this number and the criterion-1 "
                "assessment in docs/plan.md together" % (property_id, len(concluded)))

    def test_all_four_outcomes_are_reachable_on_both(self):
        seen = {p: Counter() for p in PROPERTIES}
        for property_id in PROPERTIES:
            for control_id in available():
                for as_of in INSTANTS:
                    result, _ = a_run(property_id, control_id, as_of)
                    if not result.is_blocked:
                        seen[property_id].update(v.outcome.value for v in result.verdicts)
        for property_id, tally in seen.items():
            for outcome in ("PASS", "FAIL", "UNKNOWN", "EXCLUDED"):
                assert tally[outcome] > 0, "%s never reaches %s: %s" % (
                    property_id, outcome, dict(tally))

    def test_the_two_providers_really_are_different_underneath(self):
        """A guard against the boring way this suite could pass: two adapters that turned out
        to be the same adapter. They must disagree about how they get an answer even where they
        agree about the answer."""
        first, second = (a_run(p, "checkout_money_owed", "2026-07-08T09:00")[0]
                         for p in PROPERTIES)
        assert first.provider != second.provider
        sources = [{line.source for v in result.verdicts for line in v.evidence}
                   for result in (first, second)]
        assert sources[0] and sources[1] and not (sources[0] & sources[1]), (
            "both providers cite the same evidence sources, so one of them is not really "
            "answering")


class TestHonestyAboutWhereTheEvidenceCameFrom:
    def test_a_run_over_transcoded_records_says_so_and_a_run_over_captures_does_not(self):
        """Nothing in `fixtures/demopms/` was captured from a vendor's system; it was produced
        by this repository from records that were. Both facts have to reach the screen, because
        a reader deciding how much to trust a verdict needs to know which kind of evidence it
        rests on - and v1 shipped invented fixtures without saying so."""
        flags = {p: a_run(p, "checkout_money_owed", "2026-07-08T09:00")[0].evidence_is_synthetic
                 for p in PROPERTIES}
        assert sorted(flags.values()) == [False, True], flags

    def test_every_run_names_the_body_of_evidence_it_used(self):
        for property_id in PROPERTIES:
            result, source = a_run(property_id, "checkout_money_owed", "2026-07-08T09:00")
            assert result.evidence_label
            assert source.origin.strip()

    def test_neither_provider_can_answer_a_question_its_capture_never_covered(self):
        """F19c and issue #9, on both. A capture asked about the wrong window refuses, and it
        refuses in the same place on both providers - which is what keeps the agreement above
        an agreement about the same questions."""
        for property_id in PROPERTIES:
            tenant = TenantConfig.load(property_id)
            package = next(p for p in all_providers() if p.name == tenant.provider)
            # The older capture, asked a question about a week two years after it was taken.
            adapter, _ = package.build(tenant, CAPTURES["2024-09-01T09:00"][property_id])
            with pytest.raises(ResponseUnavailable):
                from hotelcontrols.evidence import CallBudget, gather
                from hotelcontrols.spec import load
                gather(load("room_assignment_type_validity"), adapter, tenant,
                       FixedClock.at("2026-07-08T09:00", tenant.timezone), CallBudget(400))
