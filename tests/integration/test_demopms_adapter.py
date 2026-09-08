# -*- coding: utf-8 -*-
"""
The DemoPMS adapter against the transcoded responses.

The unit tests prove each transform and each path. This proves the adapter answers correctly
about the actual records the fixtures hold - the same records the vendor returned, re-encoded
into a wire format with deliberately different quirks (`tools/transcode_demopms.py`).

Every assertion here has a twin in `test_minihotel_adapter.py`, asserting the same canonical
fact about the same reservation through an API that looks nothing like it. Where the numbers
match, that is not a coincidence to be tidied away into a shared helper: it is the finding.
"""
import json
import pathlib

import pytest

from hotelcontrols.kernel import NOT_APPLICABLE, Money
from hotelcontrols.providers.base import Request, ResponseUnavailable
from hotelcontrols.providers.demopms import DemoPmsAdapter, DemoSource
from hotelcontrols.providers.demopms.paths import find_all, parse_document
from hotelcontrols.spec import SpecError, TenantConfig

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = ROOT / "spec"
FIXTURES = ROOT / "fixtures" / "demopms"


def adapter(capture="demo2026"):
    return DemoPmsAdapter(TenantConfig.load("demo"), DemoSource(capture))


@pytest.fixture(scope="module")
def provider_map():
    return json.loads((SPEC / "providers" / "demopms.json").read_text(encoding="utf-8"))


class TestEveryMappingResolves:
    def test_every_mapping_finds_its_field_in_its_own_probe(self, provider_map):
        """A mapping that silently matches nothing is an evidence gap that blames the hotel's
        data for a typo in our specification."""
        unresolved = []
        for mapping in provider_map["mappings"]:
            document = parse_document(
                (FIXTURES / mapping["probe"]).read_text(encoding="utf-8"))
            if not find_all(document, mapping["path"]):
                unresolved.append("%s -> %s in %s"
                                  % (mapping["canonical"], mapping["path"], mapping["probe"]))
        assert not unresolved, "\n".join(unresolved)

    def test_the_two_rate_plan_fields_are_deliberately_unmapped(self, provider_map):
        """R13. A reservation's rate code and a price-list code are different key spaces, and
        no PMS here resolves the mapping. Giving the FICTIONAL provider an endpoint the real
        one does not have would make it look better for reasons that are invention - and would
        break criterion 7 by making the two disagree."""
        mapped = {m["canonical"] for m in provider_map["mappings"]}
        assert "rate_plan.code" not in mapped
        assert "rate_plan.permitted_room_types" not in mapped

    def test_a_field_never_comes_back_as_none(self, provider_map):
        a = adapter()
        record = a.records(a.fetch(Request("bookings", {})), "reservation")[0]
        for mapping in provider_map["mappings"]:
            if mapping["endpoint"] != "bookings":
                continue
            value = a.resolve(mapping["canonical"], record)
            assert value is not None, mapping["canonical"]
            assert value.is_known or value.reason, mapping["canonical"]


class TestTheCurrencySplitSurvivesTheTranscode:
    """R9. The finding this project's kernel was designed around, on the other provider.

    The wire format here keeps an amount and its currency together, which is exactly the shape
    that could have quietly normalised the split away. It did not: the booking is still in USD
    and its own ledger still in ILS, with no exchange rate anywhere.
    """

    def test_a_booking_and_its_own_ledger_are_in_different_currencies(self):
        a = adapter("demo2024")
        bookings = a.records(a.fetch(Request("bookings", {})), "reservation")
        booking = next(b for b in bookings
                       if a.resolve("reservation.id", b).payload == "007003199")
        assert a.resolve("reservation.currency", booking).payload == "USD"

        ledger = a.fetch(Request("ledger", {"booking_ref": "007003199"}))
        balance = a.resolve("folio.balance_due", ledger)
        assert balance.payload == Money.parse("3262.5", "ILS")
        assert a.resolve("folio.currency", ledger).payload == "ILS"

    def test_the_two_amounts_refuse_to_compare(self):
        a = adapter("demo2024")
        bookings = a.records(a.fetch(Request("bookings", {})), "reservation")
        booking = next(b for b in bookings
                       if a.resolve("reservation.id", b).payload == "007003199")
        total = a.resolve("reservation.total_amount", booking)
        balance = a.resolve(
            "folio.balance_due", a.fetch(Request("ledger", {"booking_ref": "007003199"})))
        with pytest.raises(Exception):
            total.payload.compare(balance.payload)

    def test_the_overpaid_folio_is_still_negative(self):
        """Reservation 007004348 departed at -490.75 ILS: the guest overpaid and the hotel owes
        a refund. Decision D8 exists because of this one record, and it has to survive into
        every wire format or the two halves of control 6 stop being different controls."""
        a = adapter()
        balance = a.resolve(
            "folio.balance_due", a.fetch(Request("ledger", {"booking_ref": "007004348"})))
        assert balance.payload == Money.parse("-490.75", "ILS")
        assert balance.payload.is_negative

    def test_the_settled_folio_is_a_real_zero(self):
        a = adapter()
        balance = a.resolve(
            "folio.balance_due", a.fetch(Request("ledger", {"booking_ref": "007004351"})))
        assert balance.is_known and balance.payload.is_zero


class TestTheUnconfiguredSentinel:
    """R12, in this provider's spelling. The other one overloads 0 and therefore cannot say
    'this room sleeps nobody'; this one spends -1 on the gap and keeps 0 for the fact."""

    def test_twenty_three_of_twenty_eight_rooms_report_no_configured_adult_capacity(self):
        a = adapter()
        rooms = a.records(a.fetch(Request("rooms", {})), "room")
        assert len(rooms) == 28
        unknown = [r for r in rooms if not a.resolve("room.max_guests.adults", r).is_known]
        assert len(unknown) == 23, (
            "the same 23 rooms as the captured hotel - if this number moves, the transcode has "
            "changed what the property actually reports")
        assert all(v.risk == "R12" for v in
                   (a.resolve("room.max_guests.adults", r) for r in unknown))

    def test_a_configured_capacity_resolves_as_a_count(self):
        a = adapter()
        rooms = a.records(a.fetch(Request("rooms", {})), "room")
        known = [a.resolve("room.max_guests.adults", r) for r in rooms]
        known = [v for v in known if v.is_known]
        assert known and all(v.unit == "count" for v in known)


class TestOccupancyIsNestedRatherThanSibling:
    """The structural quirk this provider exists to exercise.

    The real PMS returns rooms and reservations as two sibling lists, so an occupancy segment
    carries its own room number. Here each segment is nested INSIDE its room and carries no
    room number at all - it has to read the one on the record containing it. Same canonical
    answer, opposite shapes.
    """

    def test_a_segment_reads_its_room_number_from_the_room_containing_it(self):
        a = adapter()
        segments = a.records(a.fetch(Request("occupancy", {})), "occupancy")
        assert segments
        for segment in segments:
            assert a.resolve("occupancy.room_number", segment).payload == "303"

    def test_the_room_number_is_genuinely_not_on_the_segment_itself(self):
        """A guard on the test above: if the transcode ever wrote the number onto each segment,
        the upward walk would stop being exercised and this file would prove nothing."""
        document = parse_document((FIXTURES / "occupancy.json").read_text(encoding="utf-8"))
        for segment in find_all(document, "rooms[].occupancy[]"):
            assert "room_no" not in segment

    def test_one_booking_appearing_twice_is_two_segments_and_not_a_defect(self):
        """Reservation 007003204 holds room 303 twice - 10-11 and 15-16 August. v1 read that
        repetition as the reason occupancy could not be cut into records at all."""
        a = adapter()
        segments = a.records(a.fetch(Request("occupancy", {})), "occupancy")
        assert len(segments) == 2
        assert {a.resolve("occupancy.reservation_id", s).payload for s in segments} == \
            {"007003204"}
        assert {a.resolve("occupancy.from", s).payload for s in segments} == \
            {"2024-08-10", "2024-08-15"}


class TestRecordIsolation:
    """R7. A record may read upwards; it may never read sideways."""

    def test_a_stay_reads_the_booking_that_contains_it_and_not_the_next_one(self):
        a = adapter()
        response = a.fetch(Request("bookings", {}))
        bookings = a.records(response, "reservation")
        stays = a.records(response, "stay")

        # Every stay's reservation id is one that exists, and the first booking's stays all
        # carry the FIRST booking's id - not the second's, which is what a sideways read gives.
        ids = {a.resolve("reservation.id", b).payload for b in bookings}
        resolved = [a.resolve("reservation.id", s).payload for s in stays]
        assert resolved and set(resolved) <= ids
        first = a.resolve("reservation.id", bookings[0]).payload
        assert resolved[0] == first

    def test_a_direct_booking_does_not_borrow_a_channel_confirmation(self):
        a = adapter()
        bookings = a.records(a.fetch(Request("bookings", {})), "reservation")
        resolved = [a.resolve("reservation.channel_confirmation_id", b) for b in bookings]
        direct = [v for v in resolved if v.payload is NOT_APPLICABLE]
        assert direct, "no direct bookings in this evidence, so the guard is untested"
        assert all(v.is_known for v in direct), (
            "'there was no channel' is a fact, not a gap")


class TestAbsenceAndEmptiness:
    def test_a_null_is_treated_as_present_and_empty(self):
        """This provider writes null where the other writes an empty element. For a field whose
        absence is its own signal, both must give known(False) - control 15 depends on it."""
        a = adapter()
        bookings = a.records(a.fetch(Request("bookings", {})), "reservation")
        answers = [a.resolve("reservation.guest.id_number", b) for b in bookings]
        assert all(v.is_known for v in answers)
        assert any(v.payload is False for v in answers)

    def test_an_unset_closed_window_is_false_rather_than_unknown(self):
        """Open question 2.4. No room in this property has ever had a closed-date window set,
        on either provider - which is a fact about the hotel rather than about any API, and it
        is why `ooo_room_protection` excludes all 28 rooms instead of passing them."""
        a = adapter()
        rooms = a.records(a.fetch(Request("rooms", {})), "room")
        answers = [a.resolve("room.closed_from", r) for r in rooms]
        assert len(answers) == 28
        assert all(v.is_known and v.payload is False for v in answers)


class TestStatusVocabulary:
    """A5. The same gap as the captured hotel, in this provider's codes."""

    def test_the_unnameable_statuses_are_the_same_reservations(self):
        a = adapter()
        bookings = a.records(a.fetch(Request("bookings", {})), "reservation")
        unknown = [b for b in bookings if not a.resolve("reservation.status", b).is_known]
        assert len(unknown) == 21, (
            "15 PROV4 and 6 HOLD - the transcodings of the 15 OK4 and 6 WL the vendor returned "
            "for this window. If this number moves, the demo hotel has stopped being this one")
        assert all(a.resolve("reservation.status", b).risk == "A5" for b in unknown)

    def test_a_mapped_status_reaches_the_canonical_vocabulary(self):
        a = adapter()
        bookings = a.records(a.fetch(Request("bookings", {})), "reservation")
        statuses = {a.resolve("reservation.status", b).payload for b in bookings}
        assert {"checked_out", "cancelled", "checked_in", "confirmed"} & statuses


class TestReplayHonesty:
    def test_a_state_filter_narrows_the_population(self):
        a = adapter()
        everyone = a.records(a.fetch(Request("bookings", {})), "reservation")
        departed = a.records(
            a.fetch(Request("bookings", {"state": "DEPARTED"})), "reservation")
        assert 0 < len(departed) < len(everyone)
        for booking in departed:
            assert a.resolve("reservation.status", booking).payload == "checked_out"

    def test_a_window_the_capture_never_covered_is_refused_not_answered_emptily(self):
        with pytest.raises(ResponseUnavailable) as caught:
            adapter().fetch(Request("bookings",
                                    {"departure": {"from": "2019-01-01", "to": "2019-01-31"}}))
        assert "cannot answer that question" in str(caught.value)

    def test_the_occupancy_window_is_guarded_too(self):
        """Issue #9, which the other provider had to learn. This one was written after, so it
        checks every window by shape from the start rather than three by name."""
        with pytest.raises(ResponseUnavailable):
            adapter().fetch(Request("occupancy",
                                    {"window": {"from": "2026-07-08", "to": "2026-07-15"}}))

    def test_an_unrecognised_filter_is_refused_rather_than_ignored(self):
        """Silently dropping a filter hands the caller a WIDER population than it asked for,
        which is the one failure a bounded query exists to prevent (R1)."""
        with pytest.raises(ResponseUnavailable):
            adapter().fetch(Request("bookings", {"some_filter_we_invented": "x"}))

    def test_a_ledger_nobody_captured_is_an_evidence_gap_with_a_reason(self):
        """The source capture holds five folios and no more, so the reservations without one
        resolve UNKNOWN - here as there. Transcoding did not fill them in."""
        with pytest.raises(ResponseUnavailable) as caught:
            adapter().fetch(Request("ledger", {"booking_ref": "007009999"}))
        assert "R1" in str(caught.value)

    def test_every_call_is_recorded_so_a_test_can_count_them(self):
        source = DemoSource("demo2026")
        a = DemoPmsAdapter(TenantConfig.load("demo"), source)
        a.fetch(Request("bookings", {}))
        a.fetch(Request("rooms", {}))
        assert len(source.calls) == 2


class TestRefusals:
    def test_a_money_field_mapped_to_a_transform_that_cannot_produce_money_is_a_spec_error(
            self):
        """R9, guarded at the mapping rather than at the value. A money-typed field resolved
        through a text transform would hand a control an amount with no currency, and it would
        look exactly like a working mapping."""
        a = adapter()
        a.mappings["folio.balance_due"] = dict(a.mappings["folio.balance_due"], transform=None)
        with pytest.raises(SpecError):
            a.resolve("folio.balance_due",
                      a.fetch(Request("ledger", {"booking_ref": "007004348"})))

    def test_an_unknown_transform_in_the_spec_raises(self):
        """An unapplied transform is a wrong value that LOOKS right, which is worse than a
        crash - so the adapter refuses rather than passing the raw value through."""
        a = adapter()
        a.mappings["reservation.status"] = dict(a.mappings["reservation.status"],
                                                transform="no_such_transform")
        record = a.records(a.fetch(Request("bookings", {})), "reservation")[0]
        with pytest.raises(SpecError):
            a.resolve("reservation.status", record)

    def test_identity_of_an_entity_with_no_identity_field_is_unknown(self):
        from hotelcontrols.providers.demopms.records import Record
        assert not adapter().identity(Record("rooms", {}, entity="unicorn")).is_known
