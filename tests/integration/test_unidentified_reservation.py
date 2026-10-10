# -*- coding: utf-8 -*-
"""
A reservation with no id - issue #85.

`reservation.id` is the IDENTITY `duplicate_channel_reservation` counts (`count_lte 1` distinct
ids per portal id), and the record identity of every reservation, stay and folio
(IDENTITY_FIELD). It was declared `absent_means: "false"`, so an EMPTY id resolved to a known
`False`, and that did two things:

  * two active bookings on one portal id, both id-less, counted as ONE reservation "False" and
    both PASSed - a duplicate reported clean by the control that exists to find duplicates (R7);
  * a per-record follow-up was built and SENT for reservation False:
    `GetReservationBalance {"ReservationNumber": False}` - a live call, against the property's
    budget (R1), about a reservation the record never named.

Found by the audit of #75's sixteen fields (follow-up 4). No committed capture has an id-less
reservation, so the documents are constructed, the smallest that show it in each provider's own
wire format. An id-less reservation is missing evidence: UNKNOWN, and no call is made for it,
through both providers (criterion 7).
"""
from collections import Counter

import pytest

from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers.base import Request
from hotelcontrols.providers.registry import all_providers
from hotelcontrols.runner import run
from hotelcontrols.spec import TenantConfig

AS_OF = "2026-07-08T09:00"
PROPERTY = {"minihotel": "sandbox", "demopms": "demo"}
BOOKINGS = {"minihotel": "GetReservationKey", "demopms": "bookings"}
FOLIO = {"minihotel": "GetReservationBalance", "demopms": "ledger"}
STATUS = {  # each provider's spelling of the two statuses used here
    "minihotel": {"confirmed": "OK", "checked_out": "OUT"},
    "demopms": {"confirmed": "BOOKED", "checked_out": "DEPARTED"},
}


def minihotel_booking(res_id, portal, status, arrival="17/07/2026", departure="19/07/2026"):
    return (
        '<Booking Portal_reservation_id="%s" Minihotel_reservation_id="%s" type="Query" '
        'createDateTime="18/06/2026" Status="%s" ModifyAllowed="YES" NumofKeys="000" '
        'source="AIRBNB" arrival_time="14:00" departure_time="11:00" market_segment="" '
        'isGroupReservation="NO">'
        '<RoomStays><RoomStay roomNumber="01" roomTypeID="DBL" roomTypeName="Double room" '
        'mealStatus="BB"></RoomStay></RoomStays>'
        '<ResGlobalInfo><GuestCount adult="1" child="0" baby="0" youth="0" />'
        '<Timespan arrival="%s" departure="%s" />'
        '<Total AmountAfterTaxes="300.00" CurrencyCode="USD" /></ResGlobalInfo></Booking>'
        % (portal, res_id, status, arrival, departure))


def demopms_booking(res_id, portal, status, arrival="17 Jul 2026", departure="19 Jul 2026"):
    return (
        '{"booking_ref": "%s", "state": "%s", "arrival": {"date": "%s", "time": "14:00"}, '
        '"departure": {"date": "%s"}, "created_on": "18 Jun 2026", '
        '"origin": {"external_ref": "%s", "channel": "AIRBNB"}, '
        '"total": {"amount": "300.00", "currency": "USD"}, "group_booking": false, '
        '"stays": [{"room_no": "01", "room_class": "DBL", "board": "BB"}]}'
        % (res_id, status, arrival, departure, portal))


def document(provider, bookings):
    """`bookings` is (id, portal id, canonical status[, arrival, departure]) per booking."""
    if provider == "minihotel":
        return ('<?xml version="1.0" encoding="utf-8"?><Bookings><Hotel id="sandbox" />%s'
                '</Bookings>' % "".join(minihotel_booking(rid, portal, STATUS[provider][st],
                                                          *dates)
                                        for rid, portal, st, *dates in bookings))
    return ('{"schema": "demopms/v1", "endpoint": "bookings", "bookings": [%s]}'
            % ", ".join(demopms_booking(rid, portal, STATUS[provider][st], *dates)
                        for rid, portal, st, *dates in bookings))


# Two active bookings sharing portal id DUPE1, neither with an id; one more alone on DUPE2,
# whose PASS must not move.
DUPLICATES = [("", "DUPE1", "confirmed"), ("", "DUPE1", "confirmed"),
              ("007000003", "DUPE2", "confirmed")]
# One checked-out booking with no id, departing inside the checkout window.
CHECKED_OUT = [("", "", "checked_out", "05/07/2026", "07/07/2026")]


class Canned:
    """Hands back one document whatever it is asked, and records what it was asked."""

    def __init__(self, body):
        self.body = body
        self.calls = []

    def fetch(self, request):
        self.calls.append(request)
        return self.body


def subject(provider, bookings):
    if provider == "demopms":  # the same dates in this provider's spelling
        bookings = [(rid, portal, st, *[_dmy_to_demopms(d) for d in dates])
                    for rid, portal, st, *dates in bookings]
    tenant = TenantConfig.load(PROPERTY[provider])
    package = next(p for p in all_providers() if p.name == provider)
    source = Canned(document(provider, bookings))
    return tenant, package.adapter(tenant, source), source


def _dmy_to_demopms(day):
    d, m, y = day.split("/")
    return "%s %s %s" % (d, ("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
                             [int(m) - 1]), y)


def a_run(control_id, provider, bookings):
    tenant, adapter, source = subject(provider, bookings)
    result = run(control_id, tenant, adapter, FixedClock.at(AS_OF, tenant.timezone))
    return result, source


@pytest.mark.parametrize("provider", sorted(PROPERTY))
class TestAnIdLessReservation:

    def test_its_id_is_unknown_never_a_known_false(self, provider):
        """CLAUDE.md, never widen: an empty reservation id is missing evidence (#85)."""
        _tenant, adapter, _source = subject(provider, DUPLICATES)
        records = adapter.records(adapter.fetch(Request(BOOKINGS[provider], {})), "reservation")
        ids = [adapter.resolve("reservation.id", r) for r in records]
        assert [v.is_known for v in ids] == [False, False, True]
        assert ids[2].payload == "007000003"
        assert all(v.reason for v in ids[:2]), "an UNKNOWN must say why"

    def test_two_id_less_bookings_on_one_portal_id_do_not_pass(self, provider):
        """The defect: both PASSed "False is the only reservation with
        reservation.channel_confirmation_id DUPE1"."""
        result, _source = a_run("duplicate_channel_reservation", provider, DUPLICATES)
        outcomes = Counter((v.record_id, v.outcome.value) for v in result.verdicts)
        assert outcomes == Counter({(None, "UNKNOWN"): 2, ("007000003", "PASS"): 1})

    def test_an_id_less_reservation_is_never_named_false(self, provider):
        result, _source = a_run("duplicate_channel_reservation", provider, DUPLICATES)
        assert not any(v.record_id is False for v in result.verdicts)

    def test_no_folio_call_is_sent_for_a_reservation_nobody_named(self, provider):
        """R1, D3: a per-record call is one call per NAMED record. Before #85 the checkout
        control asked the folio endpoint about reservation False."""
        result, source = a_run("checkout_money_owed", provider, CHECKED_OUT)
        asked = [request.endpoint for request in source.calls]
        assert FOLIO[provider] not in asked, asked
        [verdict] = result.verdicts
        assert verdict.outcome.value == "UNKNOWN"
        assert "identity is not established" in verdict.reason
