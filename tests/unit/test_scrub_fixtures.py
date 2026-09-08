# -*- coding: utf-8 -*-
"""
Fixture pseudonymisation - the thing that has to run before any captured data is committed.

Decision D6. This repository is public, and the captures came off MiniHotel's sandbox carrying
third-party guest data: 27 distinct email addresses and 30 phone numbers, several of which are
not obviously test data, plus free-text remarks naming a guest and describing an approval.
That is somebody else's personal data in somebody else's system, and it is a legal question
rather than a style one.

Three properties make a scrubber safe to build a test suite on, and all three are load-bearing:

  DETERMINISTIC   the same input always produces the same output, so fixtures are byte-stable,
                  diffs stay readable, and a test asserting a specific guest surname keeps
                  working.
  STRUCTURE-PRESERVING  an email still looks like an email, an Israeli mobile still looks like
                  an Israeli mobile. The formats ARE the evidence - every quirk this project
                  found came from a format.
  PRESENCE-PRESERVING   this is the subtle one. Control 15 asserts that
                  `reservation.guest.email` EXISTS. If the scrubber filled in a blank field,
                  it would turn a FAIL into a PASS; if it blanked a filled one, the reverse.
                  Empty stays empty, non-empty stays non-empty, always.
"""
import xml.etree.ElementTree as ET

from tools.scrub_fixtures import scrub_text, scrub_xml

SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<Bookings>
  <Booking Minihotel_reservation_id="007003199" Status="OUT">
    <PrimaryGuest>
      <Name givenName="Jon" surname="Doe" />
      <Address Street="12 Real Street" Zip="90210" City="Tel Aviv" />
      <Country CountryName="US" iso2="" iso3="" />
      <IdNumber>884412771</IdNumber>
      <Email>real.person@gmail.com</Email>
      <Phone>0501223366</Phone>
      <Fax />
      <CreditCard Type="" Number="****" NameOnCard="JON DOE" ExpirationDate="202210" />
    </PrimaryGuest>
    <ReservationRemarks>
      <PrintedRemarks>Booking id: 20240701002
Source: Qwerty</PrintedRemarks>
      <NonPrintedRemarks />
    </ReservationRemarks>
    <ResGlobalInfo>
      <GuestCount adult="2" child="0" baby="0" youth="0" />
      <Total AmountAfterTaxes="870" CurrencyCode="USD" />
    </ResGlobalInfo>
  </Booking>
</Bookings>
"""


def parsed(xml):
    return ET.fromstring(xml)


class TestItActuallyRemovesThePersonalData:
    def test_names_emails_phones_and_id_numbers_are_all_replaced(self):
        out = scrub_xml(SAMPLE)
        for original in ("Jon", "Doe", "real.person@gmail.com", "0501223366", "884412771",
                         "JON DOE", "12 Real Street", "Tel Aviv"):
            assert original not in out, "%r survived the scrubber" % original

    def test_free_text_remarks_are_replaced(self):
        """The 2026 capture carries Hebrew prose naming a guest and recording that a manager
        approved an upgrade over Telegram. That is the sharpest finding in the project and it
        is also personal data, so the fixture keeps the SHAPE and loses the content."""
        out = scrub_xml(SAMPLE)
        assert "Source: Qwerty" not in out
        assert "Booking id: 20240701002" not in out
        assert "[remark redacted" in out

    def test_the_document_is_still_valid_xml_afterwards(self):
        assert parsed(scrub_xml(SAMPLE)) is not None


class TestItPreservesWhatTheEngineReads:
    def test_identifiers_amounts_currencies_and_statuses_are_untouched(self):
        """Everything a control actually evaluates has to survive exactly. A scrubber that
        changed a balance or a status would be quietly rewriting the evidence."""
        out = parsed(scrub_xml(SAMPLE))
        booking = out.find("Booking")
        assert booking.get("Minihotel_reservation_id") == "007003199"
        assert booking.get("Status") == "OUT"
        total = booking.find("ResGlobalInfo/Total")
        assert total.get("AmountAfterTaxes") == "870"
        assert total.get("CurrencyCode") == "USD"
        assert booking.find("ResGlobalInfo/GuestCount").get("adult") == "2"

    def test_a_masked_card_number_stays_masked_rather_than_becoming_a_fake_number(self):
        """R-adjacent: the card arrives as '****' and presence is the only fact available.
        Replacing it with digits would invent evidence that the real system never gave us."""
        card = parsed(scrub_xml(SAMPLE)).find("Booking/PrimaryGuest/CreditCard")
        assert card.get("Number") == "****"

    def test_country_codes_are_not_personal_data_and_stay(self):
        assert parsed(scrub_xml(SAMPLE)).find(
            "Booking/PrimaryGuest/Country").get("CountryName") == "US"


class TestPresencePreservation:
    """The property control 15 depends on. `reservation.guest.email exists` must give the same
    verdict before and after scrubbing, or the fixture is answering a different question."""

    def test_an_empty_element_stays_empty(self):
        out = parsed(scrub_xml(SAMPLE))
        assert (out.find("Booking/PrimaryGuest/Fax").text or "") == ""
        assert (out.find("Booking/ReservationRemarks/NonPrintedRemarks").text or "") == ""

    def test_a_populated_element_stays_populated(self):
        out = parsed(scrub_xml(SAMPLE))
        assert (out.find("Booking/PrimaryGuest/Email").text or "").strip()
        assert (out.find("Booking/PrimaryGuest/Phone").text or "").strip()

    def test_an_empty_attribute_stays_empty(self):
        out = parsed(scrub_xml(SAMPLE))
        assert out.find("Booking/PrimaryGuest/Country").get("iso2") == ""

    def test_a_missing_field_is_not_invented(self):
        without = SAMPLE.replace("<Email>real.person@gmail.com</Email>", "")
        assert "<Email>" not in scrub_xml(without)


class TestDeterminism:
    def test_the_same_input_always_produces_the_same_output(self):
        """Byte-stable fixtures. Without this every re-scrub is a diff, and a test asserting a
        specific value breaks for no reason."""
        assert scrub_xml(SAMPLE) == scrub_xml(SAMPLE)

    def test_the_same_person_gets_the_same_pseudonym_everywhere(self):
        """Two reservations by one guest must still look like two reservations by one guest -
        otherwise a duplicate-detection control would see a different hotel."""
        assert scrub_text("real.person@gmail.com", "email") == \
            scrub_text("real.person@gmail.com", "email")
        assert scrub_text("a@b.com", "email") != scrub_text("c@d.com", "email")

    def test_different_field_kinds_do_not_collide(self):
        """A surname and a city that happen to share a spelling must not become the same
        token, or a fixture starts asserting a relationship that was never in the data."""
        assert scrub_text("Haifa", "surname") != scrub_text("Haifa", "city")


class TestShapePreservation:
    def test_an_email_still_looks_like_an_email(self):
        replaced = scrub_text("real.person@gmail.com", "email")
        assert "@" in replaced and replaced.endswith(".example")

    def test_a_phone_keeps_its_length_and_stays_numeric(self):
        """The formats are the evidence. A phone that stops looking like a phone stops
        exercising whatever a future control would do with one."""
        replaced = scrub_text("0501223366", "phone")
        assert len(replaced) == len("0501223366")
        assert replaced.isdigit()

    def test_an_id_number_keeps_its_length(self):
        assert len(scrub_text("884412771", "id_number")) == len("884412771")

    def test_a_name_stays_a_single_word_without_digits(self):
        replaced = scrub_text("Jon", "given_name")
        assert replaced.isalpha() and " " not in replaced
