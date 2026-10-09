# -*- coding: utf-8 -*-
"""
Slice 22 end to end: a guest asks to check out at 3 PM, and staff see the decision as a task.

    POST /api/guest/requests            reservation_id, requested_time  -> the decision
    GET  /api/guest/decisions[/<id>]    a property's decisions, each with its task
    GET  /guest   POST /guest           the staff view, and its form
    POST /guest/tasks/<action_id>       a person marks the task done or dismisses it

Over REAL evidence: the sandbox2026 capture (and its DemoPMS transcoding) describes 2026-07-08,
and holds a guest checked in and departing that day (007004343), cancelled (007004334) and
checked-out (007004348) reservations, guests departing the next day (007004338), and an
undocumented `OK4` (007004258). The decided policies belong to TEST properties built here in a
copy of spec/ - the shipped tenants decide nothing, and inventing a policy for them would be the
anti-criterion.

Protects V9 (D2 §49's Definition of Done, both providers, one decision per double submission),
V10 (an undecided parameter or an unnamed status is STAFF_REVIEW naming it), V4 (one property
cannot read another's decisions through the API), and R1 (one provider call per request).
"""
import json
import pathlib
import shutil
import urllib.parse

import pytest

from hotelcontrols.spec.registry import SPEC_DIR
from hotelcontrols.web import App

D2_49 = {"free_until": "14:00", "charge_from": "14:00", "approval_required_after": "16:00",
         "maximum_time": "18:00", "fee_per_hour": {"amount": "25.00", "currency": "USD"},
         "hour_rounding": "started_hour"}

CHECKED_IN_TODAY = "007004343"
CANCELLED = "007004334"
CHECKED_OUT = "007004348"
DEPARTS_TOMORROW = "007004338"
UNNAMED_STATUS = "007004258"         # OK4 on MiniHotel, PROV4 on DemoPMS


def _test_property(spec: pathlib.Path, tenant_id: str, like: str, policy: dict) -> None:
    """A test property: the shipped tenant's vocabulary, with a decided late-checkout policy."""
    raw = json.loads((spec / "tenants" / ("%s.json" % like)).read_text(encoding="utf-8"))
    raw["tenant_id"] = tenant_id
    raw["name"] = "TEST PROPERTY - %s's vocabulary, D2 §49's policy" % like
    raw["guest_services"] = {"LATE_CHECKOUT": policy}
    (spec / "tenants" / ("%s.json" % tenant_id)).write_text(json.dumps(raw), encoding="utf-8")


@pytest.fixture
def spec(tmp_path):
    target = tmp_path / "spec"
    shutil.copytree(SPEC_DIR, target, ignore=shutil.ignore_patterns("drafts"))
    _test_property(target, "test_d2_49", "sandbox", D2_49)
    _test_property(target, "test_d2_49_demo", "demo", D2_49)
    _test_property(target, "test_no_fee", "sandbox", dict(D2_49, fee_per_hour=None))
    return target


@pytest.fixture
def app(spec):
    return App(spec_dir=spec)


def post(app, **form):
    response = app.handle_post("/api/guest/requests", urllib.parse.urlencode(form))
    return response.status, json.loads(response.body)


def ask(app, reservation_id, at, prop="test_d2_49", **extra):
    status, body = post(app, property=prop, reservation_id=reservation_id, requested_time=at,
                        **extra)
    assert status in (200, 201), body
    return body


# --------------------------------------------------------------------------- V9
class TestTheDefinitionOfDone:

    def test_three_pm_is_approved_with_25_usd(self, app):
        """plan-v3 §5's exit test, through the API, on a real checked-in guest."""
        status, decision = post(app, property="test_d2_49", reservation_id=CHECKED_IN_TODAY,
                                requested_time="15:00")
        assert status == 201
        assert decision["decision"] == "APPROVED_WITH_FEE"
        assert decision["fee"] == "25.00 USD"          # money is a string WITH its currency
        assert decision["rule"] == "LC11-fee"
        assert decision["template"] == "LATE_CHECKOUT" and decision["template_version"] == 1
        assert decision["received_on"] == "2026-07-08"   # the capture's day, not the machine's
        assert decision["task"]["state"] == "pending"
        assert decision["task"]["severity"] == "medium"
        assert decision["task"]["audience"] == "front_office_manager"

    @pytest.mark.parametrize("at, decision, fee", [
        ("14:00", "APPROVED", None),
        ("14:01", "APPROVED_WITH_FEE", "25.00 USD"),
        ("16:00", "APPROVED_WITH_FEE", "50.00 USD"),
        ("16:01", "STAFF_REVIEW", None),
    ])
    def test_both_sides_of_both_thresholds(self, app, at, decision, fee):
        body = ask(app, CHECKED_IN_TODAY, at)
        assert (body["decision"], body["fee"]) == (decision, fee)

    def test_the_review_band_shows_the_fee_in_its_reason_and_charges_nothing(self, app):
        body = ask(app, CHECKED_IN_TODAY, "16:01")
        assert "75.00 USD" in body["reason"] and body["fee"] is None

    def test_a_request_costs_one_provider_call(self, app):
        """R1: one bulk call for the window, whatever the reservation."""
        ask(app, CHECKED_IN_TODAY, "15:00")
        assert app.provider_calls == 1


class TestTheSameDecisionThroughBothProviders:
    """Criterion 7, applied to a decision: the same hotel through MiniHotel and through DemoPMS
    gives the same decision, rule, fee and gaps for every case the capture holds."""

    @pytest.mark.parametrize("reservation_id, at", [
        (CHECKED_IN_TODAY, "15:00"), (CHECKED_IN_TODAY, "14:00"), (CHECKED_IN_TODAY, "16:01"),
        (CHECKED_IN_TODAY, "18:01"), (CANCELLED, "15:00"), (CHECKED_OUT, "15:00"),
        (DEPARTS_TOMORROW, "15:00"), (UNNAMED_STATUS, "15:00"), ("999999999", "15:00"),
    ])
    def test_same_decision(self, app, reservation_id, at):
        mini = ask(app, reservation_id, at, prop="test_d2_49")
        demo = ask(app, reservation_id, at, prop="test_d2_49_demo")
        assert mini["provider"] != demo["provider"]
        for key in ("decision", "rule", "fee", "received_on"):
            assert mini[key] == demo[key], key
        assert [g["name"] for g in mini["gaps"]] == [g["name"] for g in demo["gaps"]]


class TestOneDecisionPerDoubleSubmission:

    def test_the_same_request_twice_is_one_decision_and_one_task(self, app):
        first_status, first = post(app, property="test_d2_49", reservation_id=CHECKED_IN_TODAY,
                                   requested_time="15:00")
        second_status, second = post(app, property="test_d2_49",
                                     reservation_id=CHECKED_IN_TODAY, requested_time="15:00")
        assert (first_status, second_status) == (201, 200)
        assert first == second
        assert len(app.store.decisions(tenant_id="test_d2_49")) == 1
        assert len(app.store.actions(tenant_id="test_d2_49")) == 1

    def test_the_same_request_on_another_day_is_another_question(self, app):
        """`received_on` is in the identity: asked the day before, the guest departs
        tomorrow (LC6); asked on the day, the time rules apply."""
        before = ask(app, CHECKED_IN_TODAY, "15:00", as_of="2026-07-07")
        on_the_day = ask(app, CHECKED_IN_TODAY, "15:00")
        assert before["decision_id"] != on_the_day["decision_id"]
        assert (before["rule"], on_the_day["rule"]) == ("LC6-not-today", "LC11-fee")


# --------------------------------------------------------------------------- V10
class TestStaffReviewNamesWhy:

    def test_an_unnamed_status_is_staff_review_naming_it(self, app):
        body = ask(app, UNNAMED_STATUS, "15:00")
        assert (body["decision"], body["rule"]) == ("STAFF_REVIEW", "LC1-gaps")
        assert [g["name"] for g in body["gaps"]] == ["reservation.status"]
        assert "OK4" in body["reason"]

    def test_an_undecided_parameter_is_staff_review_naming_it(self, app):
        body = ask(app, CHECKED_IN_TODAY, "15:00", prop="test_no_fee")
        assert body["decision"] == "STAFF_REVIEW"
        assert [g["name"] for g in body["gaps"]] == ["fee_per_hour"]

    def test_a_reservation_outside_the_window_is_staff_review_not_a_denial(self, app):
        body = ask(app, "999999999", "15:00")
        assert body["decision"] == "STAFF_REVIEW"
        assert [g["name"] for g in body["gaps"]] == ["reservation"]
        assert "2026-07-07" in body["reason"] and "2026-07-09" in body["reason"]

    @pytest.mark.parametrize("prop", ["sandbox", "demo"])
    def test_the_shipped_properties_answer_staff_review_to_everything_and_say_why(
            self, app, prop):
        """The sandbox's policy is undecided, so every request is STAFF_REVIEW naming the six
        parameters - including a cancelled reservation, because a gap is checked first."""
        for reservation_id in (CHECKED_IN_TODAY, CANCELLED, CHECKED_OUT, DEPARTS_TOMORROW,
                               UNNAMED_STATUS, "999999999"):
            for at in ("10:00", "15:00", "23:59"):
                body = ask(app, reservation_id, at, prop=prop)
                assert body["decision"] == "STAFF_REVIEW", (reservation_id, at)
                names = [g["name"] for g in body["gaps"]]
                assert names[-6:] == ["free_until", "charge_from", "approval_required_after",
                                      "maximum_time", "fee_per_hour", "hour_rounding"]


# --------------------------------------------------------------------------- established
class TestEstablishedEvidence:

    @pytest.mark.parametrize("reservation_id, rule", [
        (CANCELLED, "LC2-cancelled"), (CHECKED_OUT, "LC3-checked-out")])
    def test_denied_from_evidence_and_no_task(self, app, reservation_id, rule):
        body = ask(app, reservation_id, "15:00")
        assert (body["decision"], body["rule"]) == ("DENIED", rule)
        assert body["task"] is None and body["action_id"] is None
        assert app.store.actions(tenant_id="test_d2_49") == []

    def test_departing_tomorrow_is_staff_review(self, app):
        body = ask(app, DEPARTS_TOMORROW, "15:00")
        assert (body["decision"], body["rule"]) == ("STAFF_REVIEW", "LC6-not-today")

    def test_an_approval_says_it_did_not_check_the_room_is_free(self, app):
        """G12a: no evidence can say whether another arrival needs the room, and the task a
        person carries out says so rather than implying it was checked."""
        body = ask(app, CHECKED_IN_TODAY, "13:00")
        assert body["decision"] == "APPROVED"
        assert "did not check" in body["task"]["reason"]
        assert body["task"]["severity"] == "low"

    def test_evidence_is_recorded_with_where_it_came_from(self, app):
        body = ask(app, CHECKED_IN_TODAY, "15:00")
        fields = {line["field"]: line for line in body["evidence"]}
        assert fields["reservation.status"]["value"] == "checked_in"
        assert fields["reservation.departure_date"]["value"] == "2026-07-08"
        assert all(line["source"] for line in body["evidence"])


# --------------------------------------------------------------------------- refusals
class TestMalformedRequests:
    """D12: a malformed request is refused at intake naming the field. It is not a decision and
    it is not stored."""

    @pytest.mark.parametrize("form, field", [
        ({"reservation_id": CHECKED_IN_TODAY, "requested_time": "3pm"}, "requested_time"),
        ({"reservation_id": CHECKED_IN_TODAY}, "requested_time"),
        ({"requested_time": "15:00"}, "reservation_id"),
    ])
    def test_refused_naming_the_field_and_not_stored(self, app, form, field):
        status, body = post(app, property="test_d2_49", **form)
        assert status == 400 and field in body["error"]
        assert app.store.decisions(tenant_id="test_d2_49") == []
        assert app.provider_calls == 0

    def test_an_unknown_property_is_refused_not_answered_for_another(self, app):
        """A GET falls back to the first property; a request that DECIDES something must not -
        it would be another hotel's policy applied to this guest."""
        status, body = post(app, property="nowhere", reservation_id="1", requested_time="15:00")
        assert status == 400 and "nowhere" in body["error"]
        status, body = post(app, reservation_id="1", requested_time="15:00")
        assert status == 400 and "property" in body["error"]

    def test_an_unknown_body_of_evidence_is_refused(self, app):
        status, body = post(app, property="test_d2_49", reservation_id="1",
                            requested_time="15:00", evidence="sandbox1999")
        assert status == 400 and "sandbox1999" in body["error"]

    def test_an_unreadable_date_is_refused(self, app):
        status, _body = post(app, property="test_d2_49", reservation_id="1",
                             requested_time="15:00", as_of="8 July")
        assert status == 400


# --------------------------------------------------------------------------- reading
class TestReadingDecisions:

    def test_a_property_lists_its_decisions_with_their_tasks(self, app):
        made = ask(app, CHECKED_IN_TODAY, "15:00")
        ask(app, CANCELLED, "15:00")
        listing = json.loads(app.handle("/api/guest/decisions?property=test_d2_49").body)
        assert listing["property"] == "test_d2_49"
        assert len(listing["decisions"]) == 2 and listing["pending"] == 1
        assert listing["persistent"] is False and "lost on restart" in listing["persistence"]
        one = app.handle("/api/guest/decisions/%s?property=test_d2_49" % made["decision_id"])
        assert one.status == 200 and json.loads(one.body) == made

    def test_another_property_cannot_read_a_decision(self, app):
        """V4 through the JSON API: the same 404 as a decision that never existed."""
        made = ask(app, CHECKED_IN_TODAY, "15:00")
        other = app.handle("/api/guest/decisions/%s?property=test_d2_49_demo"
                           % made["decision_id"])
        missing = app.handle("/api/guest/decisions/nope?property=test_d2_49_demo")
        assert other.status == missing.status == 404
        assert json.loads(other.body)["error"].replace(made["decision_id"], "X") == \
            json.loads(missing.body)["error"].replace("nope", "X")
        listing = json.loads(app.handle("/api/guest/decisions?property=test_d2_49_demo").body)
        assert listing["decisions"] == []


class TestTheTaskAndTheQueue:

    def test_the_findings_queue_still_lists_only_violations(self, app):
        """The /api/actions payload is the findings queue's, unchanged: a guest task is not a
        violation, and listing one there would make every client render it as one."""
        ask(app, CHECKED_IN_TODAY, "15:00")
        queue = json.loads(app.handle("/api/actions?property=test_d2_49").body)
        assert queue["records"] == [] and queue["pending"] == 0

    def test_a_person_marks_the_task_done_and_the_decision_shows_it(self, app):
        made = ask(app, CHECKED_IN_TODAY, "15:00")
        moved = app.handle_post("/api/actions/%s" % made["action_id"],
                                "property=test_d2_49&state=done")
        assert moved.status == 200
        again = json.loads(app.handle("/api/guest/decisions/%s?property=test_d2_49"
                                      % made["decision_id"]).body)
        assert again["task"]["state"] == "done"
        assert again["task"]["raised"]["decision_id"] == made["decision_id"]

    def test_the_staff_view_shows_the_decision_and_moves_its_task(self, app):
        made = ask(app, CHECKED_IN_TODAY, "15:00")
        page = app.handle("/guest?property=test_d2_49")
        assert page.status == 200
        for text in ("APPROVED WITH FEE", "25.00 USD", CHECKED_IN_TODAY, "LC11-fee",
                     "front_office_manager"):
            assert text in page.body, text
        moved = app.handle_post("/guest/tasks/%s" % made["action_id"],
                                "property=test_d2_49&state=dismissed")
        assert moved.status == 303
        assert "Dismissed" in app.handle("/guest?property=test_d2_49").body

    def test_the_staff_form_makes_a_decision_and_redirects_to_it(self, app):
        made = app.handle_post("/guest", "property=test_d2_49&reservation_id=%s"
                                         "&requested_time=16:01" % CHECKED_IN_TODAY)
        assert made.status == 303
        (decision,) = app.store.decisions(tenant_id="test_d2_49")
        assert decision.decision == "STAFF_REVIEW"
        assert decision.decision_id in made.body

    def test_the_staff_view_says_when_the_policy_is_undecided(self, app):
        page = app.handle("/guest?property=sandbox").body
        assert "not decided" in page and "free_until" in page

    def test_the_queue_page_points_at_guest_tasks_without_calling_them_violations(self, app):
        ask(app, CHECKED_IN_TODAY, "15:00")
        page = app.handle("/queue?property=test_d2_49").body
        assert "/guest?property=test_d2_49" in page
        assert "1 guest request" in page
