# -*- coding: utf-8 -*-
"""
Every DemoPMS quirk, one named function each - slice 2's suite, against a different wire format.

DemoPMS is fictional, and its quirks were chosen to be DIFFERENT from MiniHotel's rather than
convenient. A second adapter that happened to share the first one's date format and the first
one's way of saying "nobody configured this" would prove nothing at all: it would be the same
adapter twice, and the canonical boundary would still be untested.

    quirk                    MiniHotel                     DemoPMS
    -----------------------  ----------------------------  ------------------------------
    dates                    three formats, all numeric    one format, with a month NAME
    "nobody configured this" the number 0 (R10, R12)       the sentinel -1, and 0 is real
    money                    amount and currency in        one self-describing object
                             different parts of the
                             response (R9)
    booleans                 "YES"/"NO", "true", "C"/"D"   real JSON booleans, and words
    status codes             per-property, unmapped        per-property, unmapped -> UNKNOWN
                             -> UNKNOWN (A5)               (A5). The RULE is shared; the
                                                           vocabulary is not.

What the two must agree on is the CONTRACT, and that is asserted once for both in
tests/contract/. This file is about the quirks themselves.
"""
from decimal import Decimal

from hotelcontrols.kernel import Money
from hotelcontrols.providers.demopms import transforms as t


class TestDates:
    """The format carries a month NAME, so it cannot silently be read as either of MiniHotel's
    numeric ones. That is the point: a parser that shrugs and tries another format will one day
    read 01/02/2024 as the 2nd of January, and a misread date does not raise - it compares as a
    perfectly good date and passes the control."""

    def test_the_wire_format_parses_to_iso(self):
        answer = t.date_dmy_to_iso("08 Jul 2026")
        assert answer.is_known and answer.payload == "2026-07-08" and answer.unit == "date"

    def test_a_single_digit_day_parses(self):
        assert t.date_dmy_to_iso("8 Jul 2026").payload == "2026-07-08"

    def test_a_date_in_the_other_providers_format_is_refused_rather_than_guessed_at(self):
        """R2. The two formats are deliberately not mutually forgiving."""
        for other in ("08/07/2026", "20260708", "2026-07-08"):
            answer = t.date_dmy_to_iso(other)
            assert not answer.is_known and answer.risk == "R2", other

    def test_a_month_that_is_not_a_month_is_refused(self):
        assert not t.date_dmy_to_iso("08 Smarch 2026").is_known

    def test_a_day_that_month_does_not_have_is_refused(self):
        assert not t.date_dmy_to_iso("31 Feb 2026").is_known

    def test_an_empty_value_is_unknown_with_a_reason(self):
        answer = t.date_dmy_to_iso("")
        assert not answer.is_known and answer.reason

    def test_month_names_are_matched_without_asking_the_machines_locale(self):
        """A locale-dependent parser is a machine-dependent verdict. `%b` in strptime reads
        the C library's month names, so the same fixture would parse in CI and fail on a
        developer's laptop set to another language - and it would fail as an evidence gap,
        which is invisible. The table is explicit for that reason."""
        assert t.date_dmy_to_iso("08 JUL 2026").payload == "2026-07-08"
        assert t.date_dmy_to_iso("08 juillet 2026").is_known is False


class TestTheUnconfiguredSentinel:
    """R12's counterpart. MiniHotel overloads 0; DemoPMS spends a value it can never mean."""

    def test_the_sentinel_is_unknown_and_says_why(self):
        answer = t.sentinel_is_unknown(-1)
        assert not answer.is_known and answer.risk == "R12" and "configured" in answer.reason

    def test_a_real_number_is_known(self):
        answer = t.sentinel_is_unknown(6)
        assert answer.is_known and answer.payload == 6 and answer.unit == "count"

    def test_zero_is_a_real_zero_here_and_that_is_the_whole_contrast(self):
        """The same canonical field is unknown on both providers for DIFFERENT reasons, and on
        this one a genuine zero is expressible. MiniHotel cannot say 'this room sleeps no
        children'; 23 of its 28 rooms report 0 and every one of them means unconfigured."""
        answer = t.sentinel_is_unknown(0)
        assert answer.is_known and answer.payload == 0

    def test_something_that_is_not_a_number_is_unknown_rather_than_coerced(self):
        assert not t.sentinel_is_unknown("six").is_known


class TestMoney:
    """R9 again, from the other side. Here the currency travels WITH the amount - so the
    adapter never goes hunting for it, and the failure mode is different: not 'the currency was
    somewhere else', but 'the object arrived without one'."""

    def test_a_self_describing_amount_becomes_money(self):
        answer = t.money_object({"amount": "3262.50", "currency": "ILS"})
        assert answer.is_known
        assert answer.payload == Money(Decimal("3262.50"), "ILS")
        assert answer.unit == "ILS"

    def test_a_negative_amount_survives(self):
        """A checked-out folio CAN be negative - the guest overpaid. Decision D8 exists
        because of exactly one such record."""
        assert t.money_object({"amount": "-490.75", "currency": "ILS"}).payload.is_negative

    def test_an_amount_with_no_currency_is_unknown_not_a_bare_number(self):
        answer = t.money_object({"amount": "870.00"})
        assert not answer.is_known and answer.risk == "R9"

    def test_an_amount_that_was_never_priced_is_unknown(self):
        """DemoPMS's second way of saying 'nobody configured this', for money. It does not
        reuse the -1 sentinel: -1 is a perfectly good amount and a hotel might owe it."""
        answer = t.money_object({"amount": None, "currency": "USD"})
        assert not answer.is_known and "priced" in answer.reason

    def test_a_json_number_is_refused_because_it_is_a_float(self):
        """F10. `json.loads` produces a float for 3262.5, and summing money in binary floating
        point is how an audit engine produces a 0.01 discrepancy it cannot explain. The wire
        format carries amounts as strings; one that does not is not evidence."""
        answer = t.money_object({"amount": 3262.5, "currency": "ILS"})
        assert not answer.is_known and "string" in answer.reason

    def test_something_that_is_not_a_money_object_is_unknown(self):
        assert not t.money_object("870.00").is_known


class TestFlags:
    def test_real_json_booleans_are_read_as_booleans(self):
        assert t.json_bool(True).payload is True
        assert t.json_bool(False).payload is False

    def test_a_string_that_looks_like_a_boolean_is_refused(self):
        """MiniHotel must accept "true" and "YES" because that is what it sends. DemoPMS sends
        real booleans, so a string here means the response changed shape - and reading it
        anyway would hide that."""
        for looks_like in ("true", "YES", 1):
            assert not t.json_bool(looks_like).is_known, looks_like

    def test_presence_is_the_only_fact_a_masked_value_supports(self):
        assert t.presence_bool("4242").payload is True
        assert t.presence_bool("").payload is False


class TestCodeMaps:
    def test_housekeeping_words_map_to_the_canonical_vocabulary(self):
        assert t.clean_soiled("CLEAN").payload == "clean"
        assert t.clean_soiled("SOILED").payload == "dirty"

    def test_a_housekeeping_word_this_provider_does_not_define_is_unknown(self):
        assert not t.clean_soiled("SPARKLING").is_known

    def test_posting_direction_maps_to_the_canonical_vocabulary(self):
        assert t.charge_payment("CHARGE").payload == "charge"
        assert t.charge_payment("PAYMENT").payload == "payment"

    def test_casefolding_makes_two_spellings_of_one_code_compare_equal(self):
        """R13's rule, applied by a provider that does not have R13's disease. Comparing codes
        case-insensitively is right whether or not this particular API is inconsistent."""
        assert t.casefold("EXECUTIVE").payload == t.casefold("Executive").payload


class TestTenantVocabulary:
    """A5. The rule is identical on both providers and the vocabulary is not - which is the
    whole reason status maps live in `spec/tenants/` rather than in either adapter."""

    def test_a_mapped_code_resolves_to_its_canonical_status(self):
        answer = t.tenant_status_map("DEPARTED", mapping={"DEPARTED": "checked_out"})
        assert answer.payload == "checked_out"

    def test_an_unmapped_code_is_unknown_and_never_a_guess(self):
        answer = t.tenant_status_map("PROV4", mapping={"DEPARTED": "checked_out"})
        assert not answer.is_known and answer.risk == "A5"
        assert "PROV4" in answer.reason

    def test_a_department_nobody_has_mapped_is_unknown(self):
        assert not t.tenant_department_map("ROOMS", mapping={}).is_known


class TestText:
    def test_a_string_is_its_own_value(self):
        assert t.text("A1").payload == "A1"

    def test_a_number_where_text_was_expected_is_unknown_rather_than_stringified(self):
        """A booking reference that arrives as a JSON number would stringify differently from
        one that arrives as text - `1` and `"01"` are not the same key - and a join keyed on
        the wrong spelling matches nothing while looking like it tried."""
        assert not t.text(1).is_known


def test_every_transform_the_provider_map_can_name_is_registered():
    """A mapping naming a transform that is not here is a spec error the adapter raises on,
    because an unapplied transform is a wrong value that looks right."""
    assert t.TRANSFORMS[None] is t.text
    for name, function in t.TRANSFORMS.items():
        assert name is None or callable(function)
