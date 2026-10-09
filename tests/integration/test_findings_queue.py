# -*- coding: utf-8 -*-
"""
Slice 18's exit tests, on CAPTURED evidence and through the JSON API (plan-v3 §5, criterion V5).

    "A failed control becomes a task someone can see, mark done or dismiss, and running it
     again does not create the task twice."

ISSUE #59 - WHAT CHANGED FROM THE PLAN'S EXIT TEST 1, AND WHY
-------------------------------------------------------------
The plan named `checkout_money_owed` on sandbox2026. Measured, it has NO FAIL on any capture:
2 PASS at its default instant, 0 FAIL at every instant 2026-07-01..31, an empty population in
2024. Read literally, that exit test passes with zero records and proves nothing. So, with no
fixture edited and no FAIL invented:

  - the mapping on CAPTURED evidence is proven on the only FAIL anywhere in the evidence:
    `checkout_unrefunded_credit` on reservation 007004348 (-490.75 ILS, decision D8), severity
    `medium` and audience `finance` from its IR - on both providers;
  - money owed's 0 FAIL -> 0 records is asserted below AS A FACT ABOUT THE EVIDENCE, not as a
    proof of anything. If a capture ever holds a money-owed FAIL, that test fails, and it should;
  - money owed's own high/finance mapping is proven on a CONSTRUCTED run in
    `tests/unit/test_actions_records.py`, labelled as constructed there.
"""
import json
import re
import shutil
from datetime import datetime, timezone
from urllib.parse import quote_plus

import pytest

from hotelcontrols.kernel import FixedClock, Outcome
from hotelcontrols.spec import available, available_tenants, load
from hotelcontrols.spec.registry import SPEC_DIR
from hotelcontrols.store import RunStore
from hotelcontrols.web import App

PROPERTIES = {"sandbox": "sandbox2026", "demo": "demo2026"}
CREDIT = "checkout_unrefunded_credit"
OWED = "checkout_money_owed"
TRANSITION_AT = "2026-10-09T09:30:00+03:00"


def text_of(html: str) -> str:
    """What a reader sees with every tag stripped - criterion 2's no-styling reading."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def run(app, control_id, property_id="sandbox", evidence=None, as_of=None):
    path = "/api/run/%s?property=%s&evidence=%s" % (control_id, property_id,
                                                     evidence or PROPERTIES[property_id])
    if as_of:
        path += "&as_of=%s" % as_of
    response = app.handle(path)
    assert response.status == 200, response.body[:300]
    return json.loads(response.body)


def queue(app, property_id="sandbox"):
    response = app.handle("/api/actions?property=%s" % property_id)
    assert response.status == 200, response.body[:300]
    return json.loads(response.body)


def control_row(payload, control_id):
    (row,) = [c for c in payload["controls"] if c["control_id"] == control_id]
    return row


@pytest.fixture
def app():
    return App(clock=FixedClock(datetime.fromisoformat(TRANSITION_AT)))


# ---------------------------------------------------------------------------------------
class TestTheOneRealFailBecomesOneRecord:
    """Issue #59's replacement for exit test 1, on captured evidence."""

    def test_unrefunded_credit_creates_one_pending_record_for_007004348(self, app):
        payload = run(app, CREDIT)
        assert payload["counts"]["FAIL"] == 1          # the evidence, stated first

        (record,) = queue(app)["records"]
        ir = load(CREDIT)
        assert record["record_id"] == "007004348"
        assert record["control_id"] == CREDIT
        assert (record["severity"], record["audience"], record["type"]) == (
            "medium", "finance", "notify")
        assert (record["severity"], record["audience"]) == (
            ir["action"]["severity"], ir["action"]["audience"])     # straight from its IR
        assert record["state"] == "pending"
        assert (record["policy_version"], record["policy_digest"]) == (ir.version, ir.digest)
        assert record["raised"]["run_id"] == payload["run_id"]
        # The verdict's own reason: the amount travels WITH its currency (R9).
        assert "-490.75 ILS" in record["reason"]

    def test_running_it_again_creates_none(self, app):
        run(app, CREDIT)
        first = queue(app)["records"]
        for _ in range(4):
            run(app, CREDIT)
        assert queue(app)["records"] == first
        assert len(first) == 1

    def test_both_providers_raise_the_same_record(self, app):
        """Criterion 7, applied to a record: the same hotel through two wire formats."""
        seen = {}
        for property_id in PROPERTIES:
            run(app, CREDIT, property_id)
            (record,) = queue(app, property_id)["records"]
            seen[property_id] = tuple(record[k] for k in ("control_id", "record_id", "severity",
                                                          "audience", "type", "state",
                                                          "reason", "policy_version"))
        assert seen["sandbox"] == seen["demo"]

    def test_money_owed_has_no_fail_on_the_capture_so_it_makes_no_record(self, app):
        """#59: A FACT ABOUT THE EVIDENCE, not a proof of the mapping. Every instant in July
        2026, plus the capture's default. If this ever fails because a capture now holds a
        money-owed FAIL, the constructed proof in test_actions_records can become a real one."""
        instants = [None] + ["2026-07-%02d" % day for day in range(1, 32)]
        for as_of in instants:
            payload = run(app, OWED, as_of=as_of)
            assert payload["blocked"] or payload["counts"]["FAIL"] == 0, as_of
        assert [r for r in queue(app)["records"] if r["control_id"] == OWED] == []


# ---------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def matrix():
    """Every control x property x capture through ONE app, then each property's queue."""
    app = App()
    verdicts = {}
    for control_id in available():
        for property_id in available_tenants():
            for capture in app.captures_for(property_id):
                payload = run(app, control_id, property_id, capture)
                for v in payload["verdicts"]:
                    verdicts.setdefault((property_id, control_id, v["record_id"]),
                                        set()).add(v["outcome"])
    queued = {(p, r["control_id"], r["record_id"])
              for p in available_tenants() for r in queue(app, p)["records"]}
    return verdicts, queued


class TestNoUnknownOrExcludedVerdictCreatesARecord:
    """Exit test 3, as a property over the whole evidence: every control x property x capture.

    The queue after the full matrix must hold EXACTLY the FAILs, keyed by property, control and
    record, and nothing for any record that was only ever UNKNOWN, EXCLUDED or PASS."""

    def test_every_fail_and_nothing_else_is_in_the_queue(self, matrix):
        verdicts, queued = matrix
        failed = {key for key, outcomes in verdicts.items() if Outcome.FAIL.value in outcomes}
        assert queued == failed

    def test_no_record_that_was_only_unknown_excluded_or_pass_is_queued(self, matrix):
        verdicts, queued = matrix
        never_failed = {key for key, outcomes in verdicts.items()
                        if Outcome.FAIL.value not in outcomes}
        assert len(never_failed) > 500, "the matrix should cover hundreds of verdicts"
        assert not (queued & never_failed)

    def test_measured_the_whole_evidence_holds_two_fails(self, matrix):
        """One per provider, the same reservation. Stated so a new capture that changes it is
        noticed rather than absorbed."""
        _verdicts, queued = matrix
        assert queued == {("sandbox", CREDIT, "007004348"), ("demo", CREDIT, "007004348")}


# ---------------------------------------------------------------------------------------
class TestTheQueueStatesCoverage:
    """Exit test 2, and criterion 8 applied to a new surface: an empty queue must never read as
    'all clear'. Beside the records, each control's latest run says whether it concluded."""

    def test_a_run_that_concluded_nothing_makes_no_record_and_reads_as_no_conclusion(self, app):
        payload = run(app, "ooo_room_protection")        # 28 rooms, every one EXCLUDED
        assert payload["coverage"]["concluded"] is False
        listing = queue(app)
        assert listing["records"] == []
        row = control_row(listing, "ooo_room_protection")
        assert row["status"] == "no_conclusion"
        assert "reached no conclusion" in row["headline"]
        assert row["latest_run"]["run_id"] == payload["run_id"]

        page = text_of(app.handle("/queue?property=sandbox").body)
        assert "reached no conclusion" in page
        assert "all clear" not in page.replace("not an all-clear", "")

    def test_a_blocked_run_makes_no_record_and_reads_as_blocked(self, app):
        payload = run(app, "resource_occupancy_consistency")
        assert payload["blocked"]
        listing = queue(app)
        assert listing["records"] == []
        row = control_row(listing, "resource_occupancy_consistency")
        assert row["status"] == "blocked"
        assert row["latest_run"]["blocked"] == payload["blocked"]
        assert "counts" not in row["latest_run"]       # no counts for a run that never ran

    def test_a_control_never_run_reads_as_not_run(self, app):
        listing = queue(app)
        assert {c["status"] for c in listing["controls"]} == {"not_run"}
        assert [c["control_id"] for c in listing["controls"]] == list(available())
        assert all(c["latest_run"] is None for c in listing["controls"])

    def test_an_empty_queue_says_it_is_not_an_all_clear(self, app):
        page = text_of(app.handle("/queue?property=sandbox").body)
        assert "not an all-clear" in page
        for control_id in available():
            assert control_id in page

    def test_a_concluded_run_with_no_violation_says_what_it_concluded(self, app):
        run(app, OWED)
        row = control_row(queue(app), OWED)
        assert row["status"] == "concluded"
        assert "2 of 2" in row["headline"] and "no violation" in row["headline"]

    def test_a_concluded_run_with_a_violation_counts_it_and_points_at_the_record(self, app):
        run(app, CREDIT)
        row = control_row(queue(app), CREDIT)
        assert row["status"] == "concluded"
        assert "1 violation" in row["headline"]
        assert row["pending"] == 1

    def test_each_control_names_its_severity_and_audience_from_its_ir(self, app):
        for row in queue(app)["controls"]:
            action = load(row["control_id"])["action"]
            assert (row["severity"], row["audience"]) == (action["severity"],
                                                          action.get("audience"))


# ---------------------------------------------------------------------------------------
class TestAPersonMovesARecord:
    """States `pending -> done | dismissed`, stamped through the injected clock, with an actor
    (`operator` until slice 24). The POSTs write our own store and nothing else."""

    def _record(self, app, property_id="sandbox"):
        run(app, CREDIT, property_id)
        return queue(app, property_id)["records"][0]

    def test_marking_done_is_stamped_by_the_injected_clock(self, app):
        record = self._record(app)
        calls = app.provider_calls
        status, _ct, body = app.handle_post("/api/actions/%s?property=sandbox"
                                            % record["action_id"], "state=done")
        assert status == 200, body
        moved = json.loads(body)
        assert (moved["state"], moved["state_changed_at"], moved["state_changed_by"]) == (
            "done", TRANSITION_AT, "operator")
        assert app.provider_calls == calls             # a transition reads no evidence
        assert queue(app)["records"][0]["state"] == "done"

    def test_a_closed_record_cannot_be_moved_again(self, app):
        record = self._record(app)
        path = "/api/actions/%s?property=sandbox" % record["action_id"]
        assert app.handle_post(path, "state=dismissed").status == 200
        refused = app.handle_post(path, "state=done")
        assert refused.status == 409
        assert "dismissed" in json.loads(refused.body)["error"]

    @pytest.mark.parametrize("body", ["state=closed", "state=", "", "state=pending"])
    def test_a_state_that_is_not_a_move_is_refused(self, app, body):
        record = self._record(app)
        status = app.handle_post("/api/actions/%s?property=sandbox" % record["action_id"],
                                 body).status
        assert status in (400, 409)
        assert queue(app)["records"][0]["state"] == "pending"

    def test_one_task_reads_back_exactly_as_the_listing_shows_it(self, app):
        record = self._record(app)
        response = app.handle("/api/actions/%s?property=sandbox" % record["action_id"])
        assert response.status == 200
        assert json.loads(response.body) == record

    def test_a_later_pass_is_shown_on_both_surfaces_and_the_task_stays_pending(self, app):
        """CONSTRUCTED: no capture holds a PASS for 007004348 after its FAIL, so the later
        PASS is a Findings batch built here. What is under test is the rendering of an
        annotation the store already proves (tests/unit/test_store_actions.py)."""
        from datetime import timedelta

        from hotelcontrols.actions import Findings

        record = self._record(app)
        later = datetime.fromisoformat(record["raised"]["at"]) + timedelta(days=1)
        app.store.record_findings(Findings(
            run_id="constructed-pass", tenant_id="sandbox", control_id=CREDIT,
            policy_version=record["policy_version"], at=later, as_of="2026-07-09",
            passing=("007004348",)))
        (shown,) = queue(app)["records"]
        assert shown["state"] == "pending"
        assert shown["cleared"] == {"run_id": "constructed-pass", "at": later.isoformat(),
                                    "as_of": "2026-07-09"}
        page = text_of(app.handle("/queue?property=sandbox").body)
        assert "No longer failing as of run constructed-pass" in page
        assert page.count("Mark done") == 1                 # still offered: a person closes it

    def test_an_absent_record_is_a_404(self, app):
        assert app.handle_post("/api/actions/nope?property=sandbox", "state=done").status == 404
        assert app.handle("/api/actions/nope?property=sandbox").status == 404

    def test_the_page_moves_a_record_and_redirects_back_to_the_queue(self, app):
        record = self._record(app)
        status, _ct, body = app.handle_post("/queue/%s" % record["action_id"],
                                            "state=dismissed&property=sandbox")
        assert status == 303
        assert 'url=/queue?property=sandbox"' in body
        assert queue(app)["records"][0]["state"] == "dismissed"

    def test_the_page_offers_both_moves_for_a_pending_record_and_none_for_a_closed_one(
            self, app):
        record = self._record(app)
        page = app.handle("/queue?property=sandbox").body
        assert page.count('action="/queue/%s"' % record["action_id"]) == 2
        app.handle_post("/api/actions/%s?property=sandbox" % record["action_id"], "state=done")
        page = app.handle("/queue?property=sandbox").body
        assert 'action="/queue/%s"' % record["action_id"] not in page
        assert "operator" in text_of(page)


# ---------------------------------------------------------------------------------------
class TestRecordsForOnePropertyAreInvisibleToAnother:
    """Exit test 4 and criterion V4, against the JSON API (D3 §80). The structural half is
    `tests/unit/test_tenant_scoped_store.py`, which discovers the `actions` table."""

    @pytest.fixture
    def both(self, app):
        for property_id in PROPERTIES:
            run(app, CREDIT, property_id)
        ids = {p: queue(app, p)["records"][0]["action_id"] for p in PROPERTIES}
        assert ids["sandbox"] != ids["demo"]
        return app, ids

    def test_the_listing_holds_only_the_propertys_own_records(self, both):
        app, ids = both
        assert [r["action_id"] for r in queue(app, "demo")["records"]] == [ids["demo"]]
        assert [r["action_id"] for r in queue(app, "sandbox")["records"]] == [ids["sandbox"]]

    def test_another_propertys_record_is_the_same_404_as_a_missing_one(self, both):
        app, ids = both
        leaked = app.handle("/api/actions/%s?property=demo" % ids["sandbox"])
        missing = App().handle("/api/actions/%s?property=demo" % ids["sandbox"])
        assert leaked.status == missing.status == 404
        assert leaked.body == missing.body

    def test_another_property_cannot_move_a_record(self, both):
        app, ids = both
        assert app.handle_post("/api/actions/%s?property=demo" % ids["sandbox"],
                               "state=done").status == 404
        assert app.handle_post("/queue/%s" % ids["sandbox"],
                               "state=done&property=demo").status == 404
        assert queue(app, "sandbox")["records"][0]["state"] == "pending"


# ---------------------------------------------------------------------------------------
class TestThePersistenceIsStated:
    """Brief §8.8: the demo store is in memory. The default stays so, and the queue page SAYS
    the queue is lost on restart rather than implying a persistence it lacks."""

    def test_an_in_memory_queue_says_it_is_lost_on_restart(self):
        app = App()
        assert queue(app)["persistent"] is False
        assert "lost on restart" in queue(app)["persistence"]
        assert "lost on restart" in text_of(app.handle("/queue?property=sandbox").body)

    def test_a_file_store_does_not_say_it(self, tmp_path):
        app = App(store=RunStore(tmp_path / "runs.sqlite3"))
        assert queue(app)["persistent"] is True
        assert "lost on restart" not in text_of(app.handle("/queue?property=sandbox").body)

    def test_the_server_takes_an_opt_in_store_path_and_defaults_to_memory(self, tmp_path):
        from hotelcontrols.web import server

        assert server.parser().parse_args([]).store is None
        assert server.build_app(None).store.persistent is False
        path = tmp_path / "kept.sqlite3"
        arguments = server.parser().parse_args(["--store", str(path)])
        kept = server.build_app(arguments.store)
        assert kept.store.persistent and path.is_file()

    def test_the_compose_launcher_takes_the_same_option(self, tmp_path):
        from tools import serve

        path = tmp_path / "kept.sqlite3"
        app = serve.build_app("off", store=str(path))
        assert app.store.persistent and path.is_file()
        assert serve.build_app("off").store.persistent is False

    def test_a_record_survives_reopening_a_file_store(self, tmp_path):
        path = tmp_path / "kept.sqlite3"
        first = App(store=RunStore(path))
        run(first, CREDIT)
        action_id = queue(first)["records"][0]["action_id"]
        first.store.close()
        again = App(store=RunStore(path))
        assert [r["action_id"] for r in queue(again)["records"]] == [action_id]


# ---------------------------------------------------------------------------------------
class TestADraftFeedsNoQueue:
    """A composed draft is runnable and UNREVIEWED (D10), and its `action` block is BORROWED
    from the control whose population it borrowed. A guest-email draft over unrefunded credit's
    population FAILs two reservations, and would have raised two 'medium, finance' tasks for
    missing emails. So only reviewed controls feed the queue, and the draft's verdicts stay on
    its own run page."""

    def test_a_drafts_fail_creates_no_record(self, tmp_path):
        from tools.proposers import StubProposer

        drafts = tmp_path / "drafts"
        (drafts / "ir").mkdir(parents=True)
        for name in ("canonical_fields.json", "ir_schema.json"):
            shutil.copy(SPEC_DIR / name, drafts / name)
        app = App(proposer=StubProposer(), draft_dir=drafts)
        sentence = ('every reservation where reservation.status is not "cancelled" must have '
                    'reservation.guest.email exists')
        status, _ct, _body = app.handle_post(
            "/compose/accept", "control_id=guest_email_draft&template=%s&property=sandbox"
                               "&evidence=sandbox2026&sentence=%s" % (CREDIT, quote_plus(sentence)))
        assert status == 303
        payload = run(app, "guest_email_draft")
        assert payload["counts"]["FAIL"] == 2           # the draft does find something
        assert queue(app)["records"] == []
        assert "guest_email_draft" not in [c["control_id"] for c in queue(app)["controls"]]


# ---------------------------------------------------------------------------------------
class TestThePageEscapesWhatAProviderSupplied:

    def test_a_record_id_and_reason_from_a_provider_are_escaped(self):
        from hotelcontrols.actions import Finding, Findings

        app = App()
        at = datetime(2026, 7, 8, tzinfo=timezone.utc)
        hostile = Finding(tenant_id="sandbox", control_id=CREDIT, control_name="Credit",
                          policy_version=2, policy_digest="sha256:x", record_id="<b>r</b>",
                          severity="medium", audience="finance", kind="notify",
                          reason="<script>alert(1)</script>", run_id="run-1", raised_at=at,
                          as_of="2026-07-08", provider="constructed",
                          evidence_label="constructed")
        app.store.record_findings(Findings(run_id="run-1", tenant_id="sandbox",
                                           control_id=CREDIT, policy_version=2, at=at,
                                           as_of="2026-07-08", failing=(hostile,), passing=()))
        page = app.handle("/queue?property=sandbox").body
        assert "<script>alert(1)</script>" not in page and "<b>r</b>" not in page
        assert "&lt;script&gt;" in page


# ---------------------------------------------------------------------------------------
class TestTheQueueGoldens:
    """`fixtures/api/` gains NEW files only (the slice-18 row of the scope guard): the queue of
    each property after the whole matrix has run, and an untouched store's queue. Every existing
    golden stays byte-identical, which `test_api_goldens.py`'s rebuild test pins."""

    def _golden(self, name):
        from tools import dump_api_fixtures
        return json.loads((dump_api_fixtures.TARGET_DIR / "actions" / name)
                          .read_text(encoding="utf-8"))

    @pytest.mark.parametrize("property_id", sorted(PROPERTIES))
    def test_each_propertys_queue_after_the_matrix_holds_the_one_real_fail(self, property_id):
        payload = self._golden("%s.json" % property_id)
        assert payload["property"] == property_id
        assert [(r["control_id"], r["record_id"], r["state"]) for r in payload["records"]] == [
            (CREDIT, "007004348", "pending")]
        assert payload["persistent"] is False

    def test_an_untouched_store_queues_nothing_and_says_every_control_is_not_run(self):
        payload = self._golden("empty.sandbox.json")
        assert payload["records"] == []
        assert {c["status"] for c in payload["controls"]} == {"not_run"}
