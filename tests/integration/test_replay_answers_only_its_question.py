# -*- coding: utf-8 -*-
"""
A replayed response answers only the question it was asked - issue #71.

Each frozen source picked the FIRST response of the requested endpoint in a capture, then checked
only the windows both questions name. So a run asking `ArrivalDate` met sandbox2026's one
reservation response, recorded for `DepartureDate 2026-07-01..08-09`, found no `ArrivalDate` on
it to compare, and replayed the arrival filter over the departure window's bookings: the part of
an arrival population that happened to depart in that window, presented as the whole. Seven
controls ask an arrival or create window; three of criterion 1's five concluding controls
reached their PASSes that way. Issue #9 was the same shape of defect, closed for one window name.

The fix, on both providers (criterion 7):

  (a) an asked window the recorded question does not name is REFUSED - a population replayed
      from records selected by a different question is the answer to that other question;
  (b) a recorded narrowing the run does not ask is refused too - those records are a part of
      the population, presented as the whole;
  (c) the response that answers is the one whose recorded question COVERS the ask, whichever
      position it holds in the index - so the covering capture (step A) answers each control
      from the response recorded for its own question.
"""
import json

import pytest

from hotelcontrols.providers.base import Request, ResponseUnavailable
from hotelcontrols.providers.demopms import DemoSource
from hotelcontrols.providers.minihotel import FrozenSource

# Each provider's spelling of the same three questions.
ASK = {
    "minihotel": {
        "endpoint": "GetReservationKey",
        "departures": {"DepartureDate": {"From": "2026-07-01", "To": "2026-08-09"}},
        "arrivals": {"ArrivalDate": {"From": "2026-07-08", "To": "2026-10-06"}},
        "created": {"CreateDate": {"From": "2026-06-08", "To": "2026-07-08"}},
        "wider_arrivals": {"ArrivalDate": {"From": "2026-07-01", "To": "2026-10-06"}},
        "booking": "<Booking ",
    },
    "demopms": {
        "endpoint": "bookings",
        "departures": {"departure": {"from": "2026-07-01", "to": "2026-08-09"}},
        "arrivals": {"arrival": {"from": "2026-07-08", "to": "2026-10-06"}},
        "created": {"created": {"from": "2026-06-08", "to": "2026-07-08"}},
        "wider_arrivals": {"arrival": {"from": "2026-07-01", "to": "2026-10-06"}},
        "booking": '"booking_ref"',
    },
}
SOURCE = {"minihotel": FrozenSource, "demopms": DemoSource}
CAPTURE = {"minihotel": {"before": "sandbox2026", "cover": "sandbox2026cover"},
           "demopms": {"before": "demo2026", "cover": "demo2026cover"}}


def ask(provider, capture, question):
    source = SOURCE[provider](CAPTURE[provider][capture])
    spelling = ASK[provider]
    return source.fetch(Request(spelling["endpoint"], spelling[question]))


def bookings(provider, body):
    return body.count(ASK[provider]["booking"])


@pytest.mark.parametrize("provider", sorted(ASK))
class TestAWindowTheCaptureNeverRecordedIsRefused:

    @pytest.mark.parametrize("question", ["arrivals", "created"])
    def test_a_departure_capture_does_not_answer_another_windows_question(
            self, provider, question):
        """(a) The defect: answered, unchecked, from the departure window's bookings."""
        with pytest.raises(ResponseUnavailable, match="selected by"):
            ask(provider, "before", question)

    def test_the_question_it_was_recorded_for_is_still_answered(self, provider):
        assert bookings(provider, ask(provider, "before", "departures")) == 138


@pytest.mark.parametrize("provider", sorted(ASK))
class TestTheResponseThatAnswersIsTheOneAskedThatQuestion:
    """(c) The covering capture holds three reservation responses; the departure one is
    first in the index, and it must not answer the other two questions."""

    @pytest.mark.parametrize("question, expected", [
        ("departures", 138), ("arrivals", 385), ("created", 150)])
    def test_each_question_is_answered_from_its_own_recorded_response(
            self, provider, question, expected):
        assert bookings(provider, ask(provider, "cover", question)) == expected

    def test_a_wider_window_than_any_recorded_is_still_refused(self, provider):
        """Issue #9's guard, unchanged: covering means covering the whole ask."""
        with pytest.raises(ResponseUnavailable, match="cannot answer that question"):
            ask(provider, "cover", "wider_arrivals")


@pytest.mark.parametrize("provider", sorted(ASK))
class TestARecordedNarrowingTheRunDoesNotAskIsRefused:
    """(b) The other direction. A response recorded with an extra window holds a PART of what a
    run asking without it would see."""

    def test_records_selected_by_two_windows_do_not_answer_a_question_with_one(
            self, provider, tmp_path):
        spelling = ASK[provider]
        both = dict(spelling["arrivals"], **spelling["departures"])
        index = {"captures": {"t": {"label": "t", "captured_at": "2026-10-13",
                                    "as_of": "2026-07-08", "transcoded_from": "t"}},
                 "responses": [{"file": "only.txt", "endpoint": spelling["endpoint"],
                                "request": both, "captures": ["t"]}]}
        (tmp_path / "index.json").write_text(json.dumps(index), encoding="utf-8")
        (tmp_path / "only.txt").write_text("unused", encoding="utf-8")
        source = SOURCE[provider]("t", tmp_path)
        with pytest.raises(ResponseUnavailable, match="does not ask"):
            source.fetch(Request(spelling["endpoint"], spelling["arrivals"]))
