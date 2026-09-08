# -*- coding: utf-8 -*-
"""
Transforms - every MiniHotel quirk, one named function each.

Each rule below was found by CALLING the API, not by reading its documentation. Documentation
review got 4 of 12 risks wrong on this project, which is why every test here cites the risk id
and, where it matters, the actual record that established it.

A transform takes the raw string exactly as it appeared in the response and returns a `Value` -
never a bare Python object - so it is free to answer "I cannot tell" without inventing an
exception vocabulary on the way up.
"""
from decimal import Decimal

import pytest

from hotelcontrols.kernel import NOT_APPLICABLE, Money
from hotelcontrols.providers.minihotel import transforms as t


class TestDates:
    """R2 - MiniHotel mixes THREE date formats inside one API:

        GetReservationKey      arrival="28/08/2024"      dd/MM/yyyy
        GetReservationBalance  <Date>20240828</Date>     yyyyMMdd
        RoomStatusInquiry      from="2024-08-14"         yyyy-MM-dd
    """

    def test_each_format_parses_to_iso(self):
        assert t.date_ddmmyyyy_to_iso("28/08/2024").payload == "2024-08-28"
        assert t.date_yyyymmdd_to_iso("20240828").payload == "2024-08-28"
        assert t.date_iso_to_iso("2024-08-28").payload == "2024-08-28"

    def test_the_formats_are_deliberately_not_mutually_forgiving(self):
        """A parser that shrugs and tries the other format will one day read 01/02/2024 as the
        2nd of January. Worse, a misread date does not raise - it compares as a perfectly valid
        date and passes the control."""
        assert not t.date_ddmmyyyy_to_iso("20240828").is_known
        assert not t.date_yyyymmdd_to_iso("28/08/2024").is_known
        assert not t.date_iso_to_iso("28/08/2024").is_known

    def test_an_unparseable_date_is_refused_rather_than_guessed(self):
        rejected = t.date_ddmmyyyy_to_iso("not a date")
        assert not rejected.is_known and rejected.risk == "R2"
        assert "refusing to guess" in rejected.reason

    def test_an_impossible_date_is_refused(self):
        assert not t.date_iso_to_iso("2024-13-01").is_known

    def test_an_empty_date_is_unknown_with_a_reason(self):
        assert not t.date_ddmmyyyy_to_iso("").is_known

    def test_a_parsed_date_carries_the_date_unit_so_nobody_infers_a_time(self):
        """R3 - `createDateTime` is DATE ONLY, no time component, so same-day precision is
        impossible. The unit says so, and control 12 has to state that rather than imply it."""
        assert t.date_ddmmyyyy_to_iso("28/08/2024").unit == "date"


class TestNumbersAndMoney:
    def test_money_is_decimal_and_carries_its_currency(self):
        """R9/F10. The raw string goes straight to Decimal - no float ever exists."""
        value = t.to_money("3262.5", "ILS")
        assert value.payload == Money(Decimal("3262.5"), "ILS")
        assert isinstance(value.payload.amount, Decimal)

    def test_a_negative_balance_parses(self):
        """Reservation 007004348 departed at -490.75 ILS: the guest overpaid."""
        assert t.to_money("-490.75", "ILS").payload.amount == Decimal("-490.75")

    def test_an_amount_with_no_currency_is_unknown_not_a_bare_number(self):
        """R9. An amount whose currency we cannot establish is not comparable to anything."""
        value = t.to_money("3262.5", None)
        assert not value.is_known and value.risk == "R9"

    def test_an_unparseable_amount_is_unknown(self):
        assert not t.to_money("N/A", "ILS").is_known

    def test_an_integer_carries_the_count_unit(self):
        assert t.to_int("2").payload == 2 and t.to_int("2").unit == "count"

    def test_zero_means_unconfigured_not_zero(self):
        """R10/R12 - 23 of 28 sandbox rooms report adult capacity 0, and per-room prices come
        back 0 on bookings that were demonstrably paid for. Reading those as real zeroes turns
        a configuration gap into a wall of FAILs, which is 'never widen a verdict' inverted."""
        unset = t.zero_is_unknown("0", "count")
        assert not unset.is_known and unset.risk == "R12"
        assert "unconfigured" in unset.reason
        assert t.zero_is_unknown("1", "count").payload == 1

    def test_zero_is_unknown_keeps_a_capacity_integral(self):
        assert t.zero_is_unknown("2", "count").payload == 2

    def test_zero_is_unknown_on_an_amount_returns_money(self):
        assert t.zero_is_unknown("150", "USD").payload == Money(Decimal("150"), "USD")


class TestFlags:
    def test_true_and_false(self):
        assert t.to_bool("true").payload is True
        assert t.to_bool("false").payload is False
        assert not t.to_bool("maybe").is_known

    def test_yes_and_no(self):
        assert t.yesno_to_bool("YES").payload is True
        assert t.yesno_to_bool("NO").payload is False
        assert not t.yesno_to_bool("").is_known

    def test_a_masked_card_yields_presence_only_and_never_a_number(self):
        """The card arrives as '****'. Presence is the only fact available - never validity,
        never the number. Inventing either would be manufacturing evidence."""
        assert t.masked_to_presence_bool("****").payload is True
        assert t.masked_to_presence_bool("").payload is False
        assert t.masked_to_presence_bool("****").payload is not "****"


class TestCodeMaps:
    def test_casefold_makes_room_type_codes_comparable(self):
        """R13 - Bulk ARI says EXECUTIVE, the room-type master says Executive, and they are the
        same type. Comparing them raw reports a data defect that does not exist."""
        assert t.casefold("EXECUTIVE").payload == t.casefold("Executive").payload

    def test_housekeeping_codes(self):
        assert t.cd_to_clean_dirty("C").payload == "clean"
        assert t.cd_to_clean_dirty("D").payload == "dirty"
        assert not t.cd_to_clean_dirty("X").is_known

    def test_debit_credit_markers(self):
        assert t.one_two_to_charge_payment("1").payload == "charge"
        assert t.one_two_to_charge_payment("2").payload == "payment"
        assert not t.one_two_to_charge_payment("3").is_known


class TestTenantMaps:
    """A5 - status codes and folio departments are customisable PER PROPERTY. Only this layer
    knows that a hotel writes 'OUT'; a control speaks 'checked_out'."""

    MAP = {"OK": "confirmed", "IN": "checked_in", "OUT": "checked_out", "CL": "cancelled"}

    def test_a_documented_code_maps(self):
        assert t.tenant_status_map("OUT", mapping=self.MAP).payload == "checked_out"

    def test_an_undocumented_code_is_unknown_never_a_guess(self):
        """OK4 appears on 32 reservations and WL on 12 - together 44 of the 217 distinct
        reservations we have ever seen, one in five - and neither is documented anywhere. A
        waitlist guess would be plausible and might be wrong, and a status decides whether a
        control applies at all."""
        for code in ("OK4", "WL", "LWP"):
            unmapped = t.tenant_status_map(code, mapping=self.MAP)
            assert not unmapped.is_known, code
            assert unmapped.risk == "A5"
            assert code in unmapped.reason

    def test_departments_are_unknown_until_a_hotel_supplies_a_map(self):
        """'RMS' is one property's posting category; there is no provider-wide vocabulary."""
        assert not t.tenant_department_map("RMS", mapping={}).is_known


class TestRegistry:
    def test_every_transform_the_provider_map_names_exists(self):
        """A mapping naming a transform nobody implemented is a spec error, and the resolver
        must raise rather than silently passing the raw string through: an unapplied transform
        is a wrong value that looks right."""
        import json
        import pathlib
        provider = json.loads(
            (pathlib.Path(__file__).resolve().parents[2] / "spec" / "providers"
             / "minihotel.json").read_text())
        named = {m.get("transform") for m in provider["mappings"]}
        missing = sorted(n for n in named if n is not None and n not in t.TRANSFORMS)
        assert not missing, missing

    def test_the_identity_transform_passes_the_raw_string_through(self):
        assert t.identity("Qwerty").payload == "Qwerty"

    def test_every_transform_returns_a_value_never_a_bare_object(self):
        from hotelcontrols.kernel import Value
        for name, function in t.TRANSFORMS.items():
            result = function("0")
            assert isinstance(result, Value), name
