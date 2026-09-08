# -*- coding: utf-8 -*-
"""
Predicates - one IR clause applied to one record's evidence.

Every predicate returns one of THREE answers: it holds, it does not, or we cannot tell.

    PredicateResult.holds = True | False | None

The third is not an error. It is what a control says when the evidence is missing, unmapped, or
- in the case that shapes this whole project - denominated in a currency that cannot be compared
to the other side (R9). The kernel already refuses those comparisons by raising; this layer's
job is to catch the refusal and record it as "cannot tell" WITH THE REASON, rather than letting
it become a crash or, far worse, a False that reads as a violation.

`test_a_refused_currency_comparison_is_cannot_tell_and_never_false` is the one to read first.
"""
from decimal import Decimal

import pytest

from hotelcontrols.evaluator import evaluate_predicate
from hotelcontrols.evidence import Bundle
from hotelcontrols.kernel import NOT_APPLICABLE, Money, Value


def bundle(fields, joins=None, related=None):
    return Bundle("reservation", "007003199", fields, related or {}, joins or {})


class TestComparison:
    def test_equals_and_not_equals(self):
        b = bundle({"reservation.status": Value.known("checked_out")})
        assert evaluate_predicate(
            {"field": "reservation.status", "operator": "equals", "value": "checked_out"},
            b).holds is True
        assert evaluate_predicate(
            {"field": "reservation.status", "operator": "not_equals", "value": "cancelled"},
            b).holds is True

    def test_ordering_against_a_literal_zero(self):
        """Control 6's whole assertion. Currency-safe by construction: zero means the same
        amount in every currency, so R9 never arises."""
        settled = bundle({"folio.balance_due": Value.known(Money.parse("0", "ILS"))})
        owed = bundle({"folio.balance_due": Value.known(Money.parse("812.5", "ILS"))})
        overpaid = bundle({"folio.balance_due": Value.known(Money.parse("-490.75", "ILS"))})
        clause = {"field": "folio.balance_due", "operator": "lte", "value": 0}
        assert evaluate_predicate(clause, settled).holds is True
        assert evaluate_predicate(clause, owed).holds is False
        assert evaluate_predicate(clause, overpaid).holds is True

    def test_a_refused_currency_comparison_is_cannot_tell_and_never_false(self):
        """R9, and THE test in this file.

        Reservation 007003199 reports 870 USD while its own folio reports 3262.5 ILS, and no
        exchange rate exists anywhere in the API. A `False` here would be reported as a
        violation - the engine accusing a hotel of a discrepancy it invented by comparing two
        incomparable numbers.
        """
        b = bundle({"folio.balance_due": Value.known(Money.parse("3262.5", "ILS")),
                    "reservation.total_amount": Value.known(Money.parse("870", "USD"))})
        result = evaluate_predicate(
            {"field": "folio.balance_due", "operator": "equals",
             "compare_to": "reservation.total_amount"}, b)
        assert result.holds is None
        assert "R9" in result.reason or "exchange rate" in result.reason

    def test_an_unknown_value_is_cannot_tell_and_never_false(self):
        """The rule that keeps the system honest. A balance that was never established is not
        a balance of zero and is not a violation."""
        b = bundle({"folio.balance_due": Value.unknown("the folio call failed", risk="R1")})
        result = evaluate_predicate(
            {"field": "folio.balance_due", "operator": "lte", "value": 0}, b)
        assert result.holds is None
        assert "folio call failed" in result.reason

    def test_matches_ignore_case(self):
        """R13 - ARI says EXECUTIVE, the room-type master says Executive, same type."""
        b = bundle({"stay.room_type": Value.known("EXECUTIVE"),
                    "room.type": Value.known("executive")})
        assert evaluate_predicate(
            {"field": "stay.room_type", "operator": "matches_ignore_case",
             "compare_to": "room.type"}, b).holds is True


class TestExistence:
    def test_exists_and_not_exists(self):
        b = bundle({"reservation.guest.email": Value.known("a@example.example"),
                    "reservation.guest.phone": Value.known("")})
        assert evaluate_predicate(
            {"field": "reservation.guest.email", "operator": "exists"}, b).holds is True
        assert evaluate_predicate(
            {"field": "reservation.guest.phone", "operator": "exists"}, b).holds is False

    def test_zero_exists_but_false_does_not(self):
        """A settled folio balance of 0 must not read as an absent field. Written with `is`
        because in Python `0 == False`."""
        assert evaluate_predicate(
            {"field": "x", "operator": "exists"},
            bundle({"x": Value.known(Money.parse("0", "ILS"))})).holds is True
        assert evaluate_predicate(
            {"field": "x", "operator": "exists"}, bundle({"x": Value.known(False)})).holds \
            is False

    def test_not_applicable_does_not_exist_but_is_still_known(self):
        """R7. 'There was no channel, so there is no confirmation number' is a FACT. It does
        not exist, and that is a definite answer rather than a gap."""
        result = evaluate_predicate(
            {"field": "reservation.channel_confirmation_id", "operator": "exists"},
            bundle({"reservation.channel_confirmation_id": Value.known(NOT_APPLICABLE)}))
        assert result.holds is False

    def test_exists_on_an_unknown_field_cannot_tell(self):
        assert evaluate_predicate(
            {"field": "x", "operator": "exists"},
            bundle({"x": Value.unknown("never fetched")})).holds is None


class TestMembership:
    def test_in_against_a_literal_list(self):
        b = bundle({"stay.rate_code": Value.known("CORP1")})
        assert evaluate_predicate(
            {"field": "stay.rate_code", "operator": "in", "value": ["CORP1", "CORP2"]},
            b).holds is True
        assert evaluate_predicate(
            {"field": "stay.rate_code", "operator": "not_in", "value": ["CORP1"]},
            b).holds is False

    def test_in_against_a_set_reference(self):
        """Control 1b: is this room's type one of the DEFINED types? The set arrives in the
        bundle as one value holding the whole collection."""
        b = bundle({"room.type": Value.known("dbl"),
                    "room_type.code": Value.known(("dbl", "twin", "sng"))})
        assert evaluate_predicate(
            {"field": "room.type", "operator": "in", "compare_to": "room_type.code"},
            b).holds is True

    def test_a_type_the_master_does_not_define_is_a_definite_no(self):
        """R11 - rooms 9900/9901/9902 carry type 'double', which getRoomTypes does not define.
        A real latent defect in live data, and the control must report it rather than shrug."""
        b = bundle({"room.type": Value.known("double"),
                    "room_type.code": Value.known(("dbl", "twin", "sng"))})
        assert evaluate_predicate(
            {"field": "room.type", "operator": "in", "compare_to": "room_type.code"},
            b).holds is False

    def test_membership_against_an_unavailable_set_cannot_tell(self):
        """Not False. An empty or unfetched set would otherwise report every room's type as
        undefined - a wall of violations about a property whose data is fine."""
        b = bundle({"room.type": Value.known("dbl"),
                    "room_type.code": Value.unknown("the reference could not be fetched")})
        assert evaluate_predicate(
            {"field": "room.type", "operator": "in", "compare_to": "room_type.code"},
            b).holds is None

    def test_in_against_a_tenant_setting(self):
        """Control 15's scope. Which rate categories carry the requirement is the hotel's
        policy, and v1 carried a placeholder string here instead."""
        b = bundle({"stay.rate_code": Value.known("CORP1")})
        assert evaluate_predicate(
            {"field": "stay.rate_code", "operator": "in",
             "tenant_setting": "nominated_rate_codes"}, b,
            settings={"nominated_rate_codes": ["CORP1"]}).holds is True
        assert evaluate_predicate(
            {"field": "stay.rate_code", "operator": "in",
             "tenant_setting": "nominated_rate_codes"}, b,
            settings={"nominated_rate_codes": []}).holds is False


class TestIntervals:
    """Control 1d: does the arrival fall inside the room's out-of-service window?

    v1 declared `within` in its schema, used it in two controls, and implemented none of it -
    so every record came back UNKNOWN (F2).
    """

    def test_a_date_inside_the_window(self):
        b = bundle({"reservation.arrival_date": Value.known("2026-07-15", unit="date"),
                    "room.closed_from": Value.known("2026-07-01", unit="date"),
                    "room.closed_to": Value.known("2026-07-31", unit="date")})
        assert evaluate_predicate(
            {"field": "reservation.arrival_date", "operator": "within",
             "interval": {"start": "room.closed_from", "end": "room.closed_to"}},
            b).holds is True

    def test_a_date_outside_the_window(self):
        b = bundle({"reservation.arrival_date": Value.known("2026-08-15", unit="date"),
                    "room.closed_from": Value.known("2026-07-01", unit="date"),
                    "room.closed_to": Value.known("2026-07-31", unit="date")})
        assert evaluate_predicate(
            {"field": "reservation.arrival_date", "operator": "within",
             "interval": {"start": "room.closed_from", "end": "room.closed_to"}},
            b).holds is False

    def test_the_boundaries_are_inclusive(self):
        """A room closed from the 1st is closed ON the 1st. Excluding the boundary would let
        an arrival on the first day of an out-of-service window pass."""
        for arrival in ("2026-07-01", "2026-07-31"):
            b = bundle({"reservation.arrival_date": Value.known(arrival, unit="date"),
                        "room.closed_from": Value.known("2026-07-01", unit="date"),
                        "room.closed_to": Value.known("2026-07-31", unit="date")})
            assert evaluate_predicate(
                {"field": "reservation.arrival_date", "operator": "within",
                 "interval": {"start": "room.closed_from", "end": "room.closed_to"}},
                b).holds is True, arrival

    def test_an_open_ended_window_is_still_a_window(self):
        """A room closed from a date with no end is closed indefinitely. Treating the missing
        end as 'no window' would silently pass every future arrival - and all 28 sandbox rooms
        return these fields empty, so this path is the one that will actually run first."""
        b = bundle({"reservation.arrival_date": Value.known("2027-01-01", unit="date"),
                    "room.closed_from": Value.known("2026-07-01", unit="date"),
                    "room.closed_to": Value.known(False)})
        assert evaluate_predicate(
            {"field": "reservation.arrival_date", "operator": "within",
             "interval": {"start": "room.closed_from", "end": "room.closed_to"}},
            b).holds is True

    def test_no_window_at_all_is_a_definite_not_within(self):
        b = bundle({"reservation.arrival_date": Value.known("2027-01-01", unit="date"),
                    "room.closed_from": Value.known(False),
                    "room.closed_to": Value.known(False)})
        assert evaluate_predicate(
            {"field": "reservation.arrival_date", "operator": "within",
             "interval": {"start": "room.closed_from", "end": "room.closed_to"}},
            b).holds is False

    def test_an_unknown_bound_cannot_tell(self):
        """A window whose start we could not read is not a window we know to be absent."""
        b = bundle({"reservation.arrival_date": Value.known("2027-01-01", unit="date"),
                    "room.closed_from": Value.unknown("unparseable date", risk="R2"),
                    "room.closed_to": Value.known(False)})
        assert evaluate_predicate(
            {"field": "reservation.arrival_date", "operator": "within",
             "interval": {"start": "room.closed_from", "end": "room.closed_to"}},
            b).holds is None

    def test_not_within_is_the_negation(self):
        b = bundle({"reservation.arrival_date": Value.known("2026-07-15", unit="date"),
                    "room.closed_from": Value.known("2026-07-01", unit="date"),
                    "room.closed_to": Value.known("2026-07-31", unit="date")})
        assert evaluate_predicate(
            {"field": "reservation.arrival_date", "operator": "not_within",
             "interval": {"start": "room.closed_from", "end": "room.closed_to"}},
            b).holds is False


class TestReferenceExistence:
    def test_reference_exists_when_the_join_matched(self):
        b = bundle({"room.number": Value.known("303")}, joins={"room": Value.known(True)})
        assert evaluate_predicate(
            {"field": "room.number", "operator": "reference_exists"}, b).holds is True

    def test_a_room_the_master_does_not_hold_is_a_definite_violation(self):
        """Control 1a. A stay assigned to a room that does not exist is a real finding, and it
        must be FAIL rather than UNKNOWN - we looked, and it is not there."""
        b = bundle({"room.number": Value.unknown("no room in this property matches 9999")},
                   joins={"room": Value.known(False)})
        assert evaluate_predicate(
            {"field": "room.number", "operator": "reference_exists"}, b).holds is False

    def test_an_unfetchable_reference_cannot_tell(self):
        """The distinction that matters: 'the room is not in the master' and 'we could not
        read the master' must not produce the same verdict."""
        b = bundle({"room.number": Value.unknown("reference unavailable")},
                   joins={"room": Value.unknown("the room reference could not be fetched")})
        assert evaluate_predicate(
            {"field": "room.number", "operator": "reference_exists"}, b).holds is None


class TestRefusals:
    def test_a_field_absent_from_the_bundle_cannot_tell(self):
        result = evaluate_predicate(
            {"field": "reservation.vip", "operator": "exists"}, bundle({}))
        assert result.holds is None
        assert "not among this record's evidence" in result.reason

    def test_an_aggregate_operator_at_record_level_says_so(self):
        """`count_lte` asks about a GROUP. Reaching it here means the IR is being evaluated the
        wrong way round, and saying so beats answering about one record."""
        result = evaluate_predicate(
            {"field": "reservation.id", "operator": "count_lte", "value": 1},
            bundle({"reservation.id": Value.known("007003199")}))
        assert result.holds is None
        assert "group" in result.reason

    def test_every_result_names_the_fields_it_read(self):
        """The evidence table is built from these. A verdict that cannot say which fields
        produced it is not auditable."""
        result = evaluate_predicate(
            {"field": "a", "operator": "equals", "compare_to": "b"},
            bundle({"a": Value.known("x"), "b": Value.known("x")}))
        assert set(result.fields) == {"a", "b"}

    def test_a_reason_reads_as_an_explanation_next_to_a_verdict(self):
        result = evaluate_predicate(
            {"field": "folio.balance_due", "operator": "lte", "value": 0},
            bundle({"folio.balance_due": Value.known(Money.parse("812.5", "ILS"))}))
        assert result.reason == (
            "folio.balance_due is 812.5 ILS, which does not satisfy `lte 0`")
