# -*- coding: utf-8 -*-
"""
THE PROVIDER CONTRACT - what every adapter owes, asserted once for all of them.

Review finding F9: v1 had one adapter and a claim of portability. A claim about a boundary is
worth what its enforcement is worth, so this file is the enforcement. Every test here runs
against every provider the engine can discover, and none of them names a PMS, an endpoint or a
wire format.

Canonical field names DO appear. That is the point: the canonical vocabulary IS the contract,
and "a field whose absence is not applicable resolves to the sentinel" has to be sayable once
and true everywhere, or the layers above are only portable by coincidence.

Each test names the risk it protects. The five in the slice-7 gate are:

    the full Provider protocol            TestTheProtocol
    absence means what the registry says  TestAbsenceIsAnAnswerAndTheRegistrySaysWhich
    money always carries a currency       TestMoneyIsNeverABareNumber          (R9)
    an unmapped code resolves UNKNOWN     TestTenantVocabularyIsNeverGuessedAt (A5)
    a record never reads a sibling        TestRecordIsolation                  (R7)
"""
from collections import Counter

import pytest

from hotelcontrols.kernel import NOT_APPLICABLE, Money, Value
from hotelcontrols.providers.base import (Provider, ProviderError, RecordBoundaryUnknown,
                                          Request, ResponseUnavailable)
from hotelcontrols.providers.registry import all_providers, load, names
from hotelcontrols.spec import Registry, SpecError

REGISTRY = Registry.load()

# A canonical field of each shape the contract makes a promise about. Named in CANONICAL terms,
# so this table says nothing about any PMS - it is the vocabulary every adapter speaks.
NOT_APPLICABLE_FIELD = "reservation.channel_confirmation_id"   # R7
ABSENT_MEANS_FALSE_FIELD = "reservation.guest.email"           # absence is the signal itself
STATUS_FIELD = "reservation.status"                            # A5
UNMAPPED_FIELD = "reservation.vip"                             # nobody declares this anywhere


class TestTheRegistryItself:
    def test_more_than_one_provider_is_registered(self):
        """A guard on every test below. One provider makes this whole suite vacuous - it would
        pass by describing a single adapter to itself, which is exactly the state v1 was in."""
        assert len(all_providers()) >= 2, names()

    def test_a_provider_can_be_loaded_by_name(self):
        for name in names():
            assert load(name).name == name

    def test_an_unknown_provider_is_refused_by_name_rather_than_returning_nothing(self):
        """"The provider you asked for does not exist" and "the provider answered nothing" are
        different facts, and conflating them sends somebody looking for missing data that was
        never the problem."""
        with pytest.raises(KeyError):
            load("a-pms-nobody-has-written")


class TestTheProtocol:
    """Slice 7 gate: every provider implements the full `Provider` protocol."""

    def test_the_adapter_satisfies_the_protocol(self, provider):
        assert isinstance(provider.adapter, Provider), provider.name

    def test_the_adapter_names_itself_and_the_name_is_how_it_is_registered(self, provider):
        assert provider.adapter.name == provider.name

    def test_every_declared_capture_can_actually_be_opened(self, provider):
        """A capture named in the package and missing from the fixture set is a provider that
        looks runnable and is not."""
        for capture in provider.package.captures:
            assert provider.package.frozen(capture) is not None, capture

    def test_a_source_says_whether_its_evidence_is_real(self, provider):
        """Not all evidence is equal. A run over records this repository produced rather than
        captured must announce it, or it is a lie by omission - so the flag is part of the
        contract rather than one provider's private habit."""
        assert isinstance(provider.source.is_synthetic, bool)
        assert provider.source.origin.strip()
        assert provider.source.as_of.strip()


class TestAbsenceIsAnAnswerAndTheRegistrySaysWhich:
    """Slice 7 gate: a missing field returns the registry's `absent_means`, identically."""

    def test_no_resolved_value_is_ever_none(self, bundles):
        """None would be a second failure vocabulary - the one callers forget to check. Every
        field a control declared is present in its bundle as a `Value`, always."""
        offenders = [(control, bundle.record_id, name)
                     for control, bundle in bundles
                     for name, value in bundle.fields.items()
                     if not isinstance(value, Value)]
        assert not offenders, offenders[:5]

    def test_every_unknown_carries_a_reason(self, bundles):
        """An UNKNOWN whose reason is blank tells a hotel nothing about what to fix, and
        "connect this to enable the control" is the product path that depends on it."""
        offenders = [(control, bundle.record_id, name)
                     for control, bundle in bundles
                     for name, value in bundle.fields.items()
                     if not value.is_known and not (value.reason or "").strip()]
        assert not offenders, offenders[:5]

    def test_a_field_whose_absence_is_not_applicable_reaches_the_sentinel(self, provider):
        """R7. 7 of 11 sandbox bookings are direct and carry no channel confirmation at all.
        "There is no channel confirmation because there was no channel" is a FACT, and it must
        not arrive as an empty string or as UNKNOWN - or every direct booking looks like a
        duplicate of every other one, or like an evidence gap nobody can close."""
        resolved = _resolve_over_population(provider, NOT_APPLICABLE_FIELD)
        sentinels = [v for v in resolved if v.is_known and v.payload is NOT_APPLICABLE]
        assert sentinels, (
            "%s never reaches NOT_APPLICABLE on %s, so the distinction between 'no channel' "
            "and 'we could not tell' is not being made" % (NOT_APPLICABLE_FIELD, provider.name))
        assert not any(v.is_known and v.payload == "" for v in resolved), (
            "an empty string is not the same fact as NOT_APPLICABLE")

    def test_a_field_whose_absence_is_false_is_false_rather_than_unknown(self, provider):
        """The registry says a missing email IS the signal - control 15 exists to find it. An
        adapter that returned UNKNOWN instead would turn a finding into a gap."""
        assert REGISTRY.field(ABSENT_MEANS_FALSE_FIELD).absent_means == "false"
        resolved = _resolve_over_population(provider, ABSENT_MEANS_FALSE_FIELD)
        assert any(v.is_known and v.payload is False for v in resolved), (
            "%s never reaches known(False) on %s" % (ABSENT_MEANS_FALSE_FIELD, provider.name))
        assert all(v.is_known for v in resolved), (
            "a field whose absence is its own answer must never be UNKNOWN for being absent")

    def test_every_provider_offers_the_same_absent_answers_for_the_same_field(self, provider):
        """The contract that makes two adapters interchangeable. Whatever a wire format does to
        say "nothing here" - an empty element, a null, a missing key - the canonical answer is
        decided by the registry and is the same on every provider."""
        for field in (NOT_APPLICABLE_FIELD, ABSENT_MEANS_FALSE_FIELD):
            spec = REGISTRY.field(field)
            for value in _resolve_over_population(provider, field):
                if not value.is_known:
                    continue
                if value.payload is NOT_APPLICABLE:
                    assert spec.absent_means == "not_applicable", field
                elif value.payload is False:
                    assert spec.absent_means in ("false", "unknown"), field


class TestMoneyIsNeverABareNumber:
    """Slice 7 gate: money always carries a currency, on both (R9)."""

    def test_every_known_amount_is_money_with_its_currency(self, bundles):
        """The failure this prevents happened live: a reservation reporting 870 USD met its own
        folio's 3262.5 ILS, with no exchange rate anywhere in the API. A bare number cannot
        refuse that comparison; `Money` does."""
        offenders = []
        for control, bundle in bundles:
            for name, value in bundle.fields.items():
                if not REGISTRY.has(name) or not REGISTRY.field(name).is_money:
                    continue
                if not value.is_known:
                    continue
                if not isinstance(value.payload, Money) or not value.unit:
                    offenders.append((control, bundle.record_id, name, repr(value.payload)))
        assert not offenders, offenders[:5]

    def test_a_money_field_reaches_a_real_amount_somewhere(self, bundles):
        """A guard on the test above: an adapter that resolved every amount to UNKNOWN would
        satisfy it vacuously, and would also be useless."""
        known = [value for _control, bundle in bundles
                 for name, value in bundle.fields.items()
                 if REGISTRY.has(name) and REGISTRY.field(name).is_money and value.is_known]
        assert known, "no amount resolves at all"
        assert all(isinstance(v.payload, Money) for v in known)

    def test_a_reservation_and_its_own_folio_are_in_different_currencies_on_both(self, provider,
                                                                                 bundles):
        """R9, the finding itself, surviving the trip through a second wire format.

        This is not a hypothetical. Reservation 007003199 reports 870 USD while its OWN folio
        reports 3262.5 ILS, in the same property, on the same reservation, with no exchange
        rate anywhere in the API. One provider keeps the two amounts in different parts of the
        response and the other keeps each with its own currency - and BOTH have to end up
        holding two amounts that refuse to meet, or a control could compare them.
        """
        totals = {v.payload.currency for v in _resolve_over_population(
            provider, "reservation.total_amount") if v.is_known}
        balances = {value.payload.currency
                    for control, bundle in bundles
                    for name, value in bundle.fields.items()
                    if name == "folio.balance_due" and value.is_known}
        assert totals and balances, (
            "%s: this evidence must hold both a reservation total and a folio balance, or the "
            "split cannot be demonstrated" % provider.name)
        assert totals != balances, (
            "%s: the currency split is the finding. If it has flattened, the transcode or the "
            "adapter has quietly normalised what the vendor actually returns" % provider.name)

    def test_two_amounts_in_different_currencies_raise_rather_than_comparing(self, provider):
        """The consequence, made mechanical. Not compare-and-warn: refuse."""
        totals = [v.payload for v in _resolve_over_population(
            provider, "reservation.total_amount") if v.is_known]
        assert totals
        with pytest.raises(Exception):
            totals[0].compare(Money(totals[0].amount, "XTS"))


class TestTenantVocabularyIsNeverGuessedAt:
    """Slice 7 gate: an unmapped status resolves UNKNOWN, on both (A5)."""

    def test_a_status_the_property_has_not_mapped_resolves_unknown_naming_the_code(
            self, provider):
        """44 of the 217 reservations this hotel has ever shown us carry a code documented
        nowhere. Silently mapping one to something plausible would include or exclude
        reservations from a control's scope invisibly - the quietest way this system could be
        wrong - so the answer is UNKNOWN and the reason names the code."""
        assert provider.tenant.known_unmapped_statuses, (
            "%s declares no deliberately-unmapped statuses, so this test would pass vacuously"
            % provider.tenant.tenant_id)

        unknowns = [v for v in _resolve_over_population(provider, STATUS_FIELD)
                    if not v.is_known]
        assert unknowns, "no reservation reaches an unnameable status on %s" % provider.name
        assert all(v.risk == "A5" for v in unknowns)
        assert any(code in v.reason
                   for v in unknowns for code in provider.tenant.known_unmapped_statuses), (
            "the reason must name the code, or a hotel cannot ask its vendor what it means")

    def test_a_mapped_status_resolves_to_the_canonical_vocabulary(self, provider):
        """The other half. A control speaks `checked_out`; only the adapter and the tenant file
        know how this property spells it."""
        canonical = {v.payload for v in _resolve_over_population(provider, STATUS_FIELD)
                     if v.is_known}
        assert canonical, "no status resolves at all on %s" % provider.name
        assert canonical <= set(provider.tenant.status_map.values())


class TestRecordIsolation:
    """Slice 7 gate: a record never reads a sibling's field, on both (R7)."""

    def test_a_record_with_no_value_of_its_own_does_not_borrow_one(self, provider):
        """The same response holds bookings that carry a channel confirmation and bookings that
        do not. A resolver that wandered sideways looking for a better answer would hand a
        direct booking somebody else's - the quietest possible way to report a duplicate that
        does not exist."""
        resolved = _resolve_over_population(provider, NOT_APPLICABLE_FIELD)
        borrowed = [v for v in resolved if v.is_known and v.payload is not NOT_APPLICABLE]
        missing = [v for v in resolved if v.is_known and v.payload is NOT_APPLICABLE]
        assert borrowed and missing, (
            "this evidence must hold both kinds in ONE response, or the test proves nothing")

    def test_no_identifier_is_spread_across_more_records_than_actually_carry_it(self, provider):
        """A sideways read does not fail loudly; it produces a value that looks fine. What it
        cannot hide is its shape - one identifier appearing on many records at once. The real
        hotel has exactly one shared portal id, on the cancel-and-recreate pair behind R7."""
        counted = Counter(v.payload for v in _resolve_over_population(
            provider, NOT_APPLICABLE_FIELD) if v.is_known and v.payload is not NOT_APPLICABLE)
        crowded = {key: n for key, n in counted.items() if n > 2}
        assert not crowded, (
            "%s: these channel confirmations appear on more than two records, which is the "
            "shape a sibling leak makes: %s" % (provider.name, crowded))

    def test_a_record_reads_the_record_containing_it(self, provider):
        """Upwards is allowed and necessary: a room stay needs the reservation's status to know
        whether the control applies to it, and that lives on the record above. Both wire
        formats have to support it - one by walking up a document tree, the other by walking up
        a path prefix - and the canonical answer is identical."""
        stays = _resolve_over_records(provider, "stay", STATUS_FIELD)
        assert stays, "no stay records in this evidence"
        assert any(v.is_known for v in stays), (
            "no stay could reach its reservation's status, so the upward walk is not working")


class TestCallGroupingAndCost:
    """R1. The cost model the population query exists to bound, on every provider."""

    def test_two_fields_from_one_response_share_a_source_key(self, provider):
        assert provider.adapter.source_key("reservation.id") == \
            provider.adapter.source_key("reservation.status")

    def test_fields_from_different_responses_do_not(self, provider):
        assert provider.adapter.source_key("reservation.id") != \
            provider.adapter.source_key("folio.balance_due")

    def test_a_folio_is_fetched_one_record_at_a_time(self, provider):
        """The fact the whole population design exists for. If a provider ever offered a bulk
        journal endpoint this test would need changing - and that change would be the news."""
        request = provider.adapter.follow_up("folio.balance_due", "some-record-id")
        assert isinstance(request, Request)
        assert "some-record-id" in str(request.params.values())

    def test_a_property_wide_field_has_no_per_record_call(self, provider):
        """Saying None here is what makes the evidence layer fetch a reference ONCE per run
        rather than once per record - the difference between 2 calls and 112 (F1)."""
        assert provider.adapter.follow_up("room.max_guests.adults", "01") is None

    def test_the_joinable_entities_all_offer_a_reference_call(self, provider):
        for entity in ("room", "room_type", "occupancy"):
            assert isinstance(provider.adapter.reference_request(entity), Request), entity

    def test_a_reference_nobody_can_fetch_says_so_rather_than_pretending(self, provider):
        """R13. No endpoint on any provider here resolves a rate plan, so the answer must be
        None - never a call we pretend to be able to make."""
        assert provider.adapter.reference_request("rate_plan") is None


class TestPublishedEvents:
    """What a PMS tells you about, in canonical names (finding F7).

    A capability rather than a wire detail, and it is allowed to DIFFER: one provider here
    publishes a room-occupancy event and the other does not, so the same control runs in real
    time on one and on a timer on the other. What must not differ is the vocabulary it is
    declared in, or the layer above could not compare a declaration against an IR.
    """

    def test_every_provider_declares_what_it_publishes(self, provider):
        events = provider.adapter.events()
        assert isinstance(events, tuple)
        assert events, (
            "%s publishes nothing at all, so every event-driven control falls back to a timer "
            "- which may be true, and has to be a stated fact rather than an empty default"
            % provider.name)

    def test_every_event_is_named_in_the_canonical_vocabulary(self, provider):
        """`reservation.updated`, not whatever the vendor calls its webhook. An IR names events
        without knowing which systems have them, so the names have to be ours."""
        for event in provider.adapter.events():
            entity, _, verb = event.partition(".")
            assert verb, "%r is not entity.verb" % event
            assert entity in REGISTRY.entities, (
                "%r names an entity the canonical registry does not define" % event)

    def test_the_declaration_is_a_set_of_names_and_not_a_promise_about_order(self, provider):
        assert len(set(provider.adapter.events())) == len(provider.adapter.events())

    def test_a_source_says_when_its_evidence_was_obtained(self, provider):
        """The freshness half of F7. `observed_at` is when the bytes were fetched, which is a
        different fact from what date they describe - and a source that cannot say makes its
        runs stale rather than fresh."""
        assert provider.source.observed_at.strip()


class TestProvenance:
    def test_every_value_says_which_system_and_which_call_produced_it(self, bundles):
        """An auditor has to know. This string is the one thing carrying a provider name that
        crosses the canonical boundary, and it crosses as data."""
        for control, bundle in bundles:
            for name, value in bundle.fields.items():
                assert value.source or not value.is_known, (control, bundle.record_id, name)

    def test_provenance_names_the_provider_and_the_call_and_no_field_path(self, provider):
        provenance = provider.adapter.provenance("folio.balance_due")
        assert provenance.startswith("pms:%s/" % provider.name)
        assert provenance.count("/") == 1, "a field path has no business in an audit line"


class TestRefusals:
    """How each provider says no. The vocabulary of refusal is part of the contract, because
    the runner turns each one into a different sentence on screen."""

    def test_a_field_no_provider_map_declares_is_a_spec_error_not_an_evidence_gap(
            self, provider):
        """An evidence gap is a statement about a HOTEL; a missing mapping is a statement about
        US. Conflating them sends somebody looking for data that was never the problem."""
        with pytest.raises(SpecError):
            provider.adapter.source_key(UNMAPPED_FIELD)

    def test_an_entity_a_response_cannot_be_cut_into_is_named_rather_than_guessed(
            self, provider):
        """A gap in this engine, reported as which gap it is - so a runner shows a sentence
        instead of a stack trace."""
        response = provider.adapter.fetch(provider.adapter.reference_request("room"))
        with pytest.raises(RecordBoundaryUnknown):
            provider.adapter.records(response, "folio")

    def test_a_capture_that_does_not_exist_is_refused_at_construction(self, provider):
        with pytest.raises(ResponseUnavailable):
            provider.package.frozen("a-capture-nobody-took")

    def test_asking_a_response_for_a_field_it_cannot_hold_is_an_unknown_not_a_crash(
            self, provider):
        """Ordinary, not exceptional: a control whose evidence spans two calls asks every
        record for everything, and "not from this one" is the common case."""
        response = provider.adapter.fetch(provider.adapter.reference_request("room"))
        rooms = provider.adapter.records(response, "room")
        answer = provider.adapter.resolve("folio.balance_due", rooms[0])
        assert not answer.is_known and "not available" in answer.reason

    def test_a_refusal_is_always_a_provider_error_a_runner_can_catch(self, provider):
        """Every way a provider says no descends from one type, so the runner has one place to
        turn a refusal into a sentence - and a new adapter cannot invent a fifth exception
        nobody catches."""
        for refusal in (RecordBoundaryUnknown, ResponseUnavailable):
            assert issubclass(refusal, ProviderError)


# --------------------------------------------------------------------------- helpers
def _resolve_over_population(provider, field_name: str):
    """One canonical field, over every reservation in this provider's booking population."""
    return _resolve_over_records(provider, "reservation", field_name)


def _resolve_over_records(provider, entity: str, field_name: str):
    """One canonical field, over every record of an entity in the population response.

    The population request comes from a shipped IR, so this helper knows no endpoint and no
    filter - it asks the same question of every provider and lets each one answer it its own
    way.
    """
    from hotelcontrols.evidence.population import build_request
    from hotelcontrols.spec import load

    ir = load("duplicate_channel_reservation" if entity == "reservation"
              else "room_assignment_type_validity")
    request = build_request(ir, provider.name, provider.clock)
    response = provider.adapter.fetch(request)
    return [provider.adapter.resolve(field_name, record)
            for record in provider.adapter.records(response, entity)]
