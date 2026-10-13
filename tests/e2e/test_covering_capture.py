# -*- coding: utf-8 -*-
"""
Issue #71, step A: the covering capture, pinned.

`sandbox2026` holds ONE reservation question - a departure window - and seven controls ask an
arrival or a create window. Replay compared windows only by name, so those questions were
answered from the departure capture unchecked. Fixing that (step B) would leave those controls
with nothing to answer from, so this capture comes first: `sandbox2026cover` is sandbox2026's
responses, reused unchanged, plus the two questions those controls actually ask.

Two read-only calls, each approved by the project owner at the time it was made (D3):

  * 2026-10-11  GetReservationKey  ArrivalDate 2026-07-08..2026-10-06 + IncludeRoomPrices
  * 2026-10-13  GetReservationKey  CreateDate  2026-06-08..2026-07-08

sent once each by `tools.probe --run` (the first needed #92 to be printed at all) and scrubbed
before staging. `demo2026cover` is the DemoPMS transcode. The demo does not offer either.

What this pins, so a change to any of it is noticed: the capture is what it says - two new
responses dated the days they were obtained, everything else sandbox2026's own and nothing
borrowed from elsewhere - and each recorded question is exactly the call that was approved.
"""
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
NEW = {
    "15_arrivals_2026-07_prices.xml": (
        "2026-10-11", {"ArrivalDate": {"From": "2026-07-08", "To": "2026-10-06"},
                       "IncludeRoomPrices": True}),
    "16_created_2026-06.xml": (
        "2026-10-13", {"CreateDate": {"From": "2026-06-08", "To": "2026-07-08"}}),
}


def index(provider_dir):
    return json.loads((ROOT / "fixtures" / provider_dir / "index.json").read_text("utf-8"))


def members(provider_dir, capture):
    return {r["file"]: r for r in index(provider_dir)["responses"]
            if capture in r.get("captures", [])}


class TestTheCaptureIsWhatItSays:

    def test_two_calls_dated_by_the_later_one(self):
        """F7: as_of is the instant the evidence describes; captured_at is when it was
        obtained - the later of the two calls, each response carrying its own day."""
        meta = index("minihotel")["captures"]["sandbox2026cover"]
        assert (meta["as_of"], meta["captured_at"], meta["calls"]) == (
            "2026-07-08", "2026-10-13", 2)

    def test_each_new_response_is_the_call_that_was_approved_on_the_day_it_was_made(self):
        """D3: what was approved is what was printed is what was sent - and is what the index
        now says the response answers. A recorded question that differed from the call would
        make every replay of it a guess (F19c)."""
        mine = members("minihotel", "sandbox2026cover")
        for name, (day, request) in NEW.items():
            assert mine[name]["endpoint"] == "GetReservationKey"
            assert mine[name]["request"] == request, name
            assert mine[name]["captured_at"] == day, name
            assert mine[name]["captures"] == ["sandbox2026cover"], (
                "a new response belongs to the new capture only - sandbox2026 is unchanged")

    def test_everything_else_is_sandbox2026s_own_and_nothing_is_borrowed_from_elsewhere(self):
        """Reused, not mixed: the covering capture is the same hotel-as-of-2026-07-08 the
        moved tests were written against, plus the two questions it lacked. Nothing from the
        2024 capture or the 2026-10-10 refresh slips in."""
        cover = set(members("minihotel", "sandbox2026cover"))
        assert cover - set(NEW) == set(members("minihotel", "sandbox2026"))

    def test_sandbox2026_itself_did_not_change(self):
        assert not set(NEW) & set(members("minihotel", "sandbox2026"))
        assert index("minihotel")["captures"]["sandbox2026"]["captured_at"] == "2026-09-08"

    @pytest.mark.parametrize("name", sorted(NEW))
    def test_the_demo_transcode_carries_the_same_two_questions(self, name):
        """Criterion 7 needs the same hotel through both providers - including the same
        recorded questions, translated, so a window refused on one is refused on the other."""
        demo = {r["transcoded_from"]: r for r in members("demopms", "demo2026cover").values()}
        assert demo[name]["captures"] == ["demo2026cover"]
        source_windows = {k for k, v in NEW[name][1].items() if isinstance(v, dict)}
        translated = {"ArrivalDate": "arrival", "CreateDate": "created"}
        assert {k for k, v in demo[name]["request"].items() if isinstance(v, dict)} == {
            translated[k] for k in source_windows}

    def test_the_demo_capture_is_demo2026_plus_the_same_two_questions(self):
        """Not "every source response": the transcoder has never carried BulkARI, so neither
        demo2026 nor this has it. The relation that matters is the one the source has."""
        demo = {r["transcoded_from"] for r in members("demopms", "demo2026cover").values()}
        before = {r["transcoded_from"] for r in members("demopms", "demo2026").values()}
        assert demo == before | set(NEW)
        meta = index("demopms")["captures"]["demo2026cover"]
        assert (meta["as_of"], meta["captured_at"]) == ("2026-07-08", "2026-10-13")
