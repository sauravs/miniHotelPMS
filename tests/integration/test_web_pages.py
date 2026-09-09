# -*- coding: utf-8 -*-
"""
THE DEMO, END TO END - every control, every body of evidence, every page.

The web layer's single job is to prove a verdict traces to the fields that produced it. So this
file does not test that pages are pretty; it tests that the full matrix RENDERS, that a run
which concluded nothing says so rather than showing four reassuring zeroes, that readiness
reaches the index, and that a stored run can be re-read without spending a provider call (R1).

Nothing here opens a socket. `handle(path)` is a pure function of the path, so the demo is
asserted as strings - which is also why these assertions are worth anything: a test that drove
a browser would be testing a browser.
"""
import json
import re

import pytest

from hotelcontrols.providers.registry import names as provider_names
from hotelcontrols.spec import available, available_tenants, load
from hotelcontrols.web import App

CONTROLS = available()
# Every property, and every body of evidence its provider can be replayed against. The matrix
# is discovered rather than listed, so a third provider or a new capture joins it by existing.
PROPERTIES = available_tenants()


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


@pytest.fixture(scope="module")
def app():
    """One app, one in-memory store, for the whole module - so history accumulates."""
    return App()


def evidence_sets(app):
    for tenant_id in PROPERTIES:
        for capture in app.captures_for(tenant_id):
            yield tenant_id, capture


# ---------------------------------------------------------------------------------------
class TestTheIndex:

    def test_it_lists_every_control_the_spec_defines(self, app):
        body = app.handle("/").body
        for control_id in CONTROLS:
            assert control_id in body, control_id

    def test_it_shows_the_sentence_each_control_came_from(self, app):
        """The chain criterion 3 is about starts at the rule as written. An index of control
        ids is an index for whoever built the engine; an index of sentences is one for the
        hotel."""
        body = text_of(app.handle("/").body)
        assert "A reservation cannot be closed while the guest still owes money." in body

    def test_criterion_10_readiness_appears_per_control_per_provider(self, app):
        """"MiniHotel 4/5 fields · DemoPMS 5/5". Finding F8: v1 had every ingredient -
        `required_evidence[].source`, `resolvable` flags, provider coverage - and surfaced none
        of it, so nothing told a customer which controls their PMS could answer."""
        body = text_of(app.handle("/").body)
        for provider in provider_names():
            assert provider in body, provider
        assert re.search(r"\d+ of \d+ fields", body), body[:400]

    def test_a_control_that_cannot_be_answered_says_what_to_connect(self, app):
        """R13 / open question 1.6. A rate code and a price-list code are different key spaces,
        so control 9 is unanswerable until the hotel supplies the mapping - and "connect this"
        is a different sentence from "this is broken"."""
        body = text_of(app.handle("/").body)
        assert "rate_plan.permitted_room_types" in body

    def test_it_offers_every_property_and_every_body_of_evidence(self, app):
        body = app.handle("/").body
        for tenant_id, capture in evidence_sets(app):
            assert capture in body, capture
            assert tenant_id in body, tenant_id


# ---------------------------------------------------------------------------------------
class TestTheFullMatrixRenders:
    """Every control × every evidence set. The assertion is deliberately weak per cell and
    total across them: nothing 500s, nothing renders empty, and every page says which control,
    which property and which evidence it is about."""

    @pytest.mark.parametrize("control_id", CONTROLS)
    def test_the_html_run_page_renders_on_every_evidence_set(self, control_id, app):
        for tenant_id, capture in evidence_sets(app):
            path = "/run/%s?property=%s&evidence=%s" % (control_id, tenant_id, capture)
            status, content_type, body = app.handle(path)
            assert status == 200, (path, body[:300])
            assert content_type.startswith("text/html")
            assert load(control_id).name in body
            assert capture in body

    @pytest.mark.parametrize("control_id", CONTROLS)
    def test_the_json_api_answers_on_every_evidence_set(self, control_id, app):
        for tenant_id, capture in evidence_sets(app):
            path = "/api/run/%s?property=%s&evidence=%s" % (control_id, tenant_id, capture)
            status, content_type, body = app.handle(path)
            assert status == 200, (path, body[:300])
            assert content_type.startswith("application/json")
            payload = json.loads(body)
            assert payload["control_id"] == control_id
            assert payload["provider"]
            assert payload["as_of"]

    @pytest.mark.parametrize("control_id", CONTROLS)
    def test_no_page_ever_shows_a_raw_python_object(self, control_id, app):
        """The cheapest possible regression guard, and it catches a real class of mistake:
        a `Value` or a `Verdict` interpolated into a template renders as `<Value object at
        0x...>`, which is a page that looks fine and says nothing."""
        for tenant_id, capture in evidence_sets(app):
            body = app.handle("/run/%s?property=%s&evidence=%s"
                              % (control_id, tenant_id, capture)).body
            assert " object at 0x" not in body


# ---------------------------------------------------------------------------------------
class TestCriterion8OnRealRuns:
    """Finding F5 against captured evidence rather than a hand-made Run."""

    def test_the_control_that_excludes_every_room_says_it_concluded_nothing(self, app):
        """`ooo_room_protection` excludes all 28 rooms, because no room in this property has
        ever had a closed-date window set (open question 2.4). That is the CORRECT answer and
        in v1 it looked exactly like a clean bill of health."""
        body = app.handle("/run/ooo_room_protection?property=sandbox&evidence=sandbox2026").body
        assert "reached no conclusion" in text_of(body).lower()
        assert 'class="tiles"' not in body

    def test_a_blocked_run_is_a_page_with_a_reason_and_no_counts(self, app):
        """`resource_occupancy_consistency` is blocked on both standard captures: its evidence
        covers one week of August 2024 and the frozen source refuses a window it never held
        (issue #9). A blocked run must show no tiles - four zeroes for a run that never
        happened is the F5 failure in its purest form."""
        status, _ct, body = app.handle(
            "/run/resource_occupancy_consistency?property=sandbox&evidence=sandbox2026")
        assert status == 200
        assert 'class="tiles"' not in body
        assert "could not" in text_of(body).lower() or "blocked" in text_of(body).lower()

    def test_a_control_that_does_conclude_shows_its_counts(self, app):
        body = app.handle(
            "/run/checkout_money_owed?property=sandbox&evidence=sandbox2026").body
        assert 'class="tiles"' in body


class TestCriterion3OnRealRuns:

    def test_a_real_verdict_lists_its_fields_with_units_and_provenance(self, app):
        """The overpaid folio: reservation 007004348 left with -490.75 ILS. Every part of that
        sentence has to be on screen - the record, the field, the amount, the CURRENCY, and
        which call produced it."""
        body = app.handle(
            "/run/checkout_unrefunded_credit?property=sandbox&evidence=sandbox2026").body
        assert "007004348" in body
        assert "-490.75 ILS" in body
        assert "folio.balance_due" in body
        assert "pms:" in body, "a verdict must name the call its evidence came from"

    def test_an_unknown_names_the_field_it_could_not_establish(self, app):
        """The commercial value of an UNKNOWN, on screen: not "we don't know" but "connect
        this and we will"."""
        body = text_of(app.handle(
            "/run/room_capacity_compliance?property=sandbox&evidence=sandbox2026").body)
        assert "room.max_guests.adults" in body


# ---------------------------------------------------------------------------------------
class TestHistoryAndStoredRuns:

    def test_a_run_is_saved_and_appears_in_its_history(self, app):
        app.handle("/run/checkout_money_owed?property=sandbox&evidence=sandbox2026")
        app.handle("/run/checkout_money_owed?property=sandbox&evidence=sandbox2024")
        body = app.handle("/history/checkout_money_owed").body
        assert "sandbox2026" in body and "sandbox2024" in body

    def test_history_is_newest_first(self, app):
        body = app.handle("/history/checkout_money_owed").body
        stamps = re.findall(r'data-created="([^"]+)"', body)
        assert stamps == sorted(stamps, reverse=True), stamps

    def test_a_stored_run_re_reads_with_zero_provider_calls(self, app):
        """R1, and the reason the store exists. Re-running to answer "what did it say?" costs
        one call per reservation on somebody else's server."""
        live = json.loads(app.handle(
            "/api/run/checkout_money_owed?property=sandbox&evidence=sandbox2026").body)
        run_id = live["run_id"]
        before = app.provider_calls
        stored = json.loads(app.handle("/api/runs/%s" % run_id).body)
        assert app.provider_calls == before, "re-reading a stored run made a provider call"
        assert stored["run_id"] == run_id
        assert [v["outcome"] for v in stored["verdicts"]] == \
               [v["outcome"] for v in live["verdicts"]]

    def test_a_stored_run_keeps_its_evidence_including_units_and_reasons(self, app):
        run_id = json.loads(app.handle(
            "/api/run/checkout_money_owed?property=sandbox&evidence=sandbox2026").body)["run_id"]
        stored = json.loads(app.handle("/api/runs/%s" % run_id).body)
        lines = [line for verdict in stored["verdicts"] for line in verdict["evidence"]]
        assert any(line["value"].endswith(" ILS") for line in lines), \
            "a stored amount without its currency is a receipt with the number missing (R9)"

    def test_an_unknown_run_id_is_a_404_and_not_an_empty_run(self, app):
        status, _ct, body = app.handle("/api/runs/deadbeefdeadbeef")
        assert status == 404
        assert "error" in json.loads(body)


class TestReadinessApi:

    @pytest.mark.parametrize("control_id", CONTROLS)
    def test_readiness_is_reported_per_control_per_provider(self, control_id, app):
        payload = json.loads(app.handle("/api/readiness/%s" % control_id).body)
        assert payload["control_id"] == control_id
        assert {p["provider"] for p in payload["providers"]} == set(provider_names())
        for report in payload["providers"]:
            assert report["total"] >= report["available"] >= 0
            assert "headline" in report

    def test_the_two_providers_are_equally_ready_for_every_control(self, app):
        """Criterion 7's readiness shadow. The two adapters map the same canonical fields, so
        a control answerable on one must be answerable on the other - and if that ever stops
        being true, the portability claim has a hole in it that the verdict tests would not
        find, because a control blocked on both providers agrees with itself."""
        for control_id in CONTROLS:
            payload = json.loads(app.handle("/api/readiness/%s" % control_id).body)
            ratios = {(p["available"], p["total"]) for p in payload["providers"]}
            assert len(ratios) == 1, (control_id, payload["providers"])


# ---------------------------------------------------------------------------------------
def test_the_demo_needs_nothing_but_the_standard_library(app):
    """Criterion 11 for the page itself: no external stylesheet, script or font."""
    pages = ["/", "/history/checkout_money_owed",
             "/run/checkout_money_owed?property=sandbox&evidence=sandbox2026"]
    for path in pages:
        body = app.handle(path).body
        assert "http://" not in body and "https://" not in body, path
        assert "<script" not in body, path


def test_no_page_ever_shows_a_double_escaped_entity(app):
    """`page()` escapes its own arguments, so a caller passing "&middot;" gets six literal
    characters on screen. It is a small bug with a loud symptom, and the only reliable way to
    catch it is to look for the shape it always takes."""
    paths = ["/", "/history/checkout_money_owed", "/nowhere",
             "/run/checkout_money_owed?property=sandbox&evidence=sandbox2026",
             "/run/ooo_room_protection?property=demo&evidence=demo2026"]
    for path in paths:
        assert "&amp;middot;" not in app.handle(path).body, path
        assert "&amp;lt;" not in app.handle(path).body, path


class TestTheReaderCanAskADifferentQuestion:
    """`?as_of=` is the one knob on this demo, and it is the one that matters.

    A body of evidence answers about the window it covers. The default is the instant the
    capture declares, and asking anything else is the reader's call - stated on the page, and
    refused rather than fudged when the capture cannot cover it.
    """

    def test_the_occupancy_control_concludes_on_the_week_its_evidence_covers(self, app):
        """Issue #9's honest ending, on screen. `resource_occupancy_consistency` is blocked on
        both standard captures because its occupancy segments cover one week of August 2024 -
        and asked about that week, it concludes perfectly well. The engine reached two PASSes
        at ANY date until the frozen source started checking every window against the capture,
        and the count went down rather than the guard going away."""
        body = app.handle("/run/resource_occupancy_consistency"
                          "?property=sandbox&evidence=sandbox2024&as_of=2024-08-14").body
        assert 'class="tiles"' in body
        assert "2024-08-14" in body

    def test_a_date_the_engine_cannot_read_is_refused_rather_than_guessed(self, app):
        """"yesterday" is a perfectly good English date and not a date this engine can act on.
        Guessing at it would move a population window silently, which is the F11 failure with
        a friendlier face."""
        status, _ct, body = app.handle(
            "/run/checkout_money_owed?property=sandbox&as_of=yesterday")
        assert status == 400
        assert "YYYY-MM-DD" in body

    def test_a_control_never_run_has_an_empty_history_that_says_so(self):
        """A fresh app, deliberately: the shared one has run everything by now. An empty
        history must read as "nothing yet" rather than as an empty table nobody explains."""
        body = App().handle("/history/room_capacity_compliance").body
        assert "has not been run" in text_of(body)

    def test_a_property_that_does_not_exist_falls_back_and_the_page_says_which(self, app):
        """A mistyped query string is not worth a refusal - but the page must never quietly
        answer about a different property than the reader asked for without saying so."""
        body = app.handle("/run/checkout_money_owed?property=nowhere").body
        assert "Property" in text_of(body)
        assert any(name in body for name in PROPERTIES)


def test_a_deployment_with_no_property_configured_says_so(tmp_path):
    """The one state that is a misconfiguration rather than a gap in the data, and it must not
    render as an empty index that looks like a working system with no controls."""
    import os
    from hotelcontrols.spec.registry import SPEC_DIR

    (tmp_path / "tenants").mkdir()
    for name in ("canonical_fields.json", "ir_schema.json", "ir", "providers"):
        os.symlink(SPEC_DIR / name, tmp_path / name)

    status, _ct, body = App(spec_dir=tmp_path).handle("/")
    assert status == 500
    assert "No property is configured" in body
