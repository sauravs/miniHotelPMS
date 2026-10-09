# -*- coding: utf-8 -*-
"""
Slice 17's exit test, against the JSON API and not the page (D3 §80): with runs for two
properties in one store, neither can read the other's.

`?property=` is still a SELECTION and not an identity until slice 24 authenticates it. What this
slice guarantees is that the selection is honoured all the way down - a property's history holds
only its own runs, another property's stored run is a 404 indistinguishable from one that never
existed, and two properties composing a draft under the same id no longer overwrite each other
(QA Q10, collision A2).

Every test protects criterion V4 (plan-v3 §7) unless it names another.
"""
import json
import re
import shutil
import urllib.parse

import pytest

from hotelcontrols.spec.registry import SPEC_DIR
from hotelcontrols.web import App
from tools.proposers import StubProposer

CONTROL = "checkout_money_owed"


def _json(app, path):
    status, _ct, body = app.handle(path)
    return status, json.loads(body)


@pytest.fixture(scope="module")
def app():
    """One store, the same control run for both properties."""
    app = App()
    for prop in ("demo", "sandbox"):
        app.handle("/api/run/%s?property=%s" % (CONTROL, prop))
    return app


def _run_id(app, prop):
    status, history = _json(app, "/api/history/%s?property=%s" % (CONTROL, prop))
    assert status == 200 and len(history["runs"]) == 1, history
    return history["runs"][0]["run_id"]


class TestHistoryIsPerProperty:

    def test_each_propertys_history_holds_only_its_own_runs(self, app):
        demo, sandbox = _run_id(app, "demo"), _run_id(app, "sandbox")
        assert demo != sandbox
        _status, history = _json(app, "/api/history/%s?property=sandbox" % CONTROL)
        assert [row["run_id"] for row in history["runs"]] == [sandbox]
        assert history["property"] == "sandbox"

    def test_the_history_page_links_each_run_with_its_property(self, app):
        body = app.handle("/history/%s?property=sandbox" % CONTROL).body
        sandbox, demo = _run_id(app, "sandbox"), _run_id(app, "demo")
        assert 'href="/api/runs/%s?property=sandbox"' % sandbox in body
        assert demo not in body


class TestAnotherPropertysRunIsA404:

    def test_a_property_reads_its_own_stored_run(self, app):
        status, payload = _json(app, "/api/runs/%s?property=sandbox" % _run_id(app, "sandbox"))
        assert status == 200 and payload["tenant_id"] == "sandbox"

    def test_another_propertys_run_is_a_404_not_a_403(self, app):
        status, payload = _json(app, "/api/runs/%s?property=sandbox" % _run_id(app, "demo"))
        assert status == 404, payload

    def test_the_404_cannot_be_told_apart_from_a_run_that_never_existed(self, app):
        """Otherwise the difference between the two messages is an oracle for which run ids
        exist in somebody else's hotel."""
        theirs = _run_id(app, "demo")
        _s, foreign = _json(app, "/api/runs/%s?property=sandbox" % theirs)
        _s, missing = _json(app, "/api/runs/%s?property=sandbox" % ("0" * len(theirs)))
        assert foreign["error"].replace(theirs, "<id>") == missing["error"].replace(
            "0" * len(theirs), "<id>")


class TestDraftsArePerProperty:
    """QA Q10, collision A2: two properties composing `late_checkout_policy`."""

    @pytest.fixture
    def composing(self, tmp_path):
        drafts = tmp_path / "drafts"
        (drafts / "ir").mkdir(parents=True)
        for name in ("canonical_fields.json", "ir_schema.json"):
            shutil.copy(SPEC_DIR / name, drafts / name)
        return App(proposer=StubProposer(), draft_dir=drafts), drafts

    @staticmethod
    def _file(app, prop, sentence):
        form = urllib.parse.urlencode({
            "control_id": "late_checkout_policy", "template": "checkout_money_owed",
            "property": prop, "sentence": sentence})
        status, _ct, body = app.handle_post("/api/compose/accept", form)
        assert status == 201, body
        return json.loads(body)

    def test_two_properties_filing_one_id_do_not_overwrite_each_other(self, composing):
        app, drafts = composing
        self._file(app, "demo", 'every reservation where reservation.status is "checked_out" '
                                "must have folio.balance_due at most 0")
        self._file(app, "sandbox", 'every reservation where reservation.status is '
                                   '"checked_out" must have folio.balance_due at most 10')
        demo = json.loads((drafts / "demo" / "ir" / "late_checkout_policy.json").read_text())
        sandbox = json.loads((drafts / "sandbox" / "ir" / "late_checkout_policy.json")
                             .read_text())
        assert demo["assertion"]["predicates"][0]["value"] == 0
        assert sandbox["assertion"]["predicates"][0]["value"] == 10

    def test_a_property_lists_only_its_own_drafts(self, composing):
        app, _drafts = composing
        self._file(app, "demo", 'every reservation where reservation.status is "checked_out" '
                                "must have folio.balance_due at most 0")
        _s, demo = _json(app, "/api/drafts?property=demo")
        _s, sandbox = _json(app, "/api/drafts?property=sandbox")
        assert [d["control_id"] for d in demo["drafts"]] == ["late_checkout_policy"]
        assert sandbox["drafts"] == []

    def test_another_propertys_draft_cannot_be_run_or_read(self, composing):
        app, _drafts = composing
        self._file(app, "demo", 'every reservation where reservation.status is "checked_out" '
                                "must have folio.balance_due at most 0")
        status, _ct, _body = app.handle("/api/run/late_checkout_policy?property=demo")
        assert status == 200
        for path in ("/api/run/late_checkout_policy?property=sandbox",
                     "/api/readiness/late_checkout_policy?property=sandbox",
                     "/api/history/late_checkout_policy?property=sandbox"):
            status, _ct, _body = app.handle(path)
            assert status == 404, path

    def test_a_draft_still_cannot_shadow_a_reviewed_control(self, composing):
        app, _drafts = composing
        form = urllib.parse.urlencode({"control_id": CONTROL, "template": CONTROL,
                                       "property": "demo", "sentence": "x"})
        status, _ct, _body = app.handle_post("/api/compose/accept", form)
        assert status == 409


def test_a_mistyped_property_is_answered_for_the_property_actually_used(app):
    """`?property=` falls back to the default when it names nothing - and the payload SAYS which
    property it answered for, so a client cannot mistake the default's history for its own."""
    _s, history = _json(app, "/api/history/%s?property=Sandbox" % CONTROL)
    assert history["property"] == "demo"
    assert re.fullmatch(r"[0-9a-f]+", history["runs"][0]["run_id"])
