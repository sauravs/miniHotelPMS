# -*- coding: utf-8 -*-
"""
Slice 19's exit tests on CAPTURED evidence, through the app: email, opt-in, behind two locks.

    "the finance team is emailed when a control finds money owed, and nobody is emailed
     because a test ran."

Every app here is wired with `RecordingNotifier` - a list, not a network. The SMTP backend's
locks are `tests/unit/test_notifiers_refuse_in_tests.py`.

ON ISSUE #59, AGAIN. The plan's sentence names money owed, which has no FAIL on any capture.
The one email the captured evidence produces is for `checkout_unrefunded_credit` on 007004348,
to `finance` - the same real FAIL slice 18 was proven on, on both providers.
"""
import json
import re
from datetime import datetime

import pytest

from hotelcontrols.evidence.budget import CallBudget
from hotelcontrols.evidence.cache import ResponseCache
from hotelcontrols.evidence.population import population
from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers import registry as providers
from hotelcontrols.spec import TenantConfig, available, available_tenants, load
from hotelcontrols.web import App
from tools.notifiers import RecordingNotifier

PROPERTIES = {"sandbox": "sandbox2026", "demo": "demo2026"}
CREDIT = "checkout_unrefunded_credit"
NOW = "2026-10-09T09:30:00+03:00"
PUBLIC = "http://controls.example.test"

# Every audience any shipped rule names, each routed to one fictional address.
AUDIENCES = sorted({load(c)["action"]["audience"] for c in available()})
GUEST_FIELDS = ("reservation.guest.given_name", "reservation.guest.surname",
                "reservation.guest.email", "reservation.guest.phone",
                "reservation.guest.id_number")


def wired(routes=None):
    notifier = RecordingNotifier(routes if routes is not None else
                                 {a: ("%s@example.test" % a,) for a in AUDIENCES})
    app = App(notifier=notifier, public_url=PUBLIC,
              clock=FixedClock(datetime.fromisoformat(NOW)))
    return app, notifier


def run(app, control_id, property_id="sandbox", evidence=None):
    response = app.handle("/api/run/%s?property=%s&evidence=%s"
                          % (control_id, property_id, evidence or PROPERTIES[property_id]))
    assert response.status == 200, response.body[:300]
    return json.loads(response.body)


def queue(app, property_id="sandbox"):
    return json.loads(app.handle("/api/actions?property=%s" % property_id).body)


def text_of(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


# ---------------------------------------------------------------------------------------
class TestAFailEmailsItsAudienceOnce:
    """Exit test 1."""

    @pytest.mark.parametrize("property_id", sorted(PROPERTIES))
    def test_the_real_fail_emails_finance_once(self, property_id):
        app, notifier = wired()
        run(app, CREDIT, property_id)
        (message,) = notifier.sent
        assert message.to == ("finance@example.test",)
        assert message.audience == "finance"
        assert "007004348" in message.subject + message.body
        assert "-490.75 ILS" in message.body             # the amount, with its currency

    def test_running_it_again_sends_nothing(self):
        app, notifier = wired()
        for _ in range(5):
            run(app, CREDIT)
        assert len(notifier.sent) == 1

    def test_the_link_leads_to_the_task_on_its_propertys_queue(self):
        app, notifier = wired()
        run(app, CREDIT)
        (record,) = queue(app)["records"]
        assert "%s/queue?property=sandbox#task-%s" % (PUBLIC, record["action_id"]) in \
            notifier.sent[0].body

    def test_the_task_records_that_it_was_emailed(self):
        app, _notifier = wired()
        run(app, CREDIT)
        listing = queue(app)
        (record,) = listing["records"]
        assert record["delivery"] == {"channel": "email", "sent_at": NOW, "note": None}
        assert listing["email"] == {"wired": True, "via": "recording"}
        assert "Emailed to finance" in text_of(app.handle("/queue?property=sandbox").body)


# ---------------------------------------------------------------------------------------
class TestNothingIsSentForARunThatSaidNothing:
    """Exit test 2, by name: the all-excluded case and the blocked case (brief §8.5)."""

    def test_a_run_that_concluded_nothing_sends_nothing(self):
        app, notifier = wired()
        payload = run(app, "ooo_room_protection")      # all 28 rooms EXCLUDED
        assert payload["coverage"]["concluded"] is False
        assert notifier.sent == []

    def test_a_blocked_run_sends_nothing_to_the_audience(self):
        app, notifier = wired()
        payload = run(app, "resource_occupancy_consistency")
        assert payload["blocked"]
        assert notifier.sent == []

    def test_the_whole_evidence_sends_exactly_two_emails_one_per_provider(self):
        """Every control x property x capture: two FAILs exist, so two emails, each to finance.
        Nothing UNKNOWN, EXCLUDED, blocked or unconcluded sends anything."""
        app, notifier = wired()
        for control_id in available():
            for property_id in available_tenants():
                for capture in app.captures_for(property_id):
                    run(app, control_id, property_id, capture)
        assert sorted((m.tenant_id, m.audience) for m in notifier.sent) == [
            ("demo", "finance"), ("sandbox", "finance")]


# ---------------------------------------------------------------------------------------
class TestAMissingRouteIsStated:

    def test_no_route_leaves_the_task_unsent_saying_so(self):
        app, notifier = wired(routes={})
        run(app, CREDIT)
        assert notifier.sent == []
        (record,) = queue(app)["records"]
        assert record["state"] == "pending"
        assert record["delivery"] == {"channel": None, "sent_at": None,
                                      "note": "no route configured for audience finance"}
        assert "no route configured for audience finance" in \
            text_of(app.handle("/queue?property=sandbox").body)


# ---------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def guest_details():
    """Every guest name, email, phone and id number in the 2026 captures, per provider, read
    through the adapters - so the no-PII test below checks against what is really there."""
    found = set()
    for property_id, capture in PROPERTIES.items():
        tenant = TenantConfig.load(property_id)
        adapter, source = providers.load(tenant.provider).build(tenant, capture)
        records = population(load("required_reservation_fields"), adapter,
                             FixedClock.at(source.as_of, tenant.timezone),
                             ResponseCache(adapter.fetch, CallBudget(1000)))
        for record in records:
            for field in GUEST_FIELDS:
                value = adapter.resolve(field, record)
                if value.is_known and isinstance(value.payload, str) and value.payload.strip():
                    found.add(value.payload.strip())
    # Measured, not assumed: the captures hold phone "numbers" of two and three digits (`04`,
    # `08`, `265`) and a four-digit id. A value that short cannot be told apart from the day in
    # `2026-07-08` or a digit of an amount, so purely numeric values under five digits are left
    # out - they identify nobody. Every name, every email and every longer number stays in.
    found = {d for d in found if not (d.isdigit() and len(d) < 5)}
    assert len(found) > 50, "the PII probe found almost nothing - it would pass vacuously"
    return found


class TestNoEmailCarriesGuestDetails:
    """Exit test 4 and criterion V6: no email body contains a guest name, email, phone or card
    token. Over the rendered message for every FAIL in every capture - and, because two FAILs
    are a thin sample, over a message rendered for EVERY record of every run as if it had
    failed (labelled constructed; `render_message` is the same function either way)."""

    def _leaks(self, message, details):
        text = message.subject + "\n" + message.body
        return sorted(d for d in details if re.search(r"(?<!\w)%s(?!\w)" % re.escape(d), text)) \
            + (["****"] if "****" in text else [])

    def test_every_real_fail_in_every_capture(self, guest_details):
        app, notifier = wired()
        for control_id in available():
            for property_id in available_tenants():
                for capture in app.captures_for(property_id):
                    run(app, control_id, property_id, capture)
        assert len(notifier.sent) == 2
        for message in notifier.sent:
            assert self._leaks(message, guest_details) == []

    def test_constructed_every_record_of_every_run_as_if_it_had_failed(self, guest_details):

        from hotelcontrols.actions import ActionRecord, amounts_of, render_message, task_link

        app, _notifier = wired()
        checked = 0
        for control_id in available():
            ir = load(control_id)
            for property_id, capture in PROPERTIES.items():
                stored = app.store.load(run(app, control_id, property_id, capture)["run_id"],
                                        tenant_id=property_id)
                for verdict in stored.verdicts:
                    record = ActionRecord(
                        action_id="constructed", tenant_id=property_id, control_id=control_id,
                        control_name=ir.name, policy_version=ir.version,
                        policy_digest=ir.digest, record_id=verdict.record_id or "none",
                        severity=ir["action"]["severity"],
                        audience=ir["action"].get("audience"), kind=ir["action"]["type"],
                        reason=verdict.reason, raised_by_run=stored.run_id,
                        raised_at=stored.created_at, as_of=stored.as_of,
                        provider=stored.provider, evidence_label=stored.evidence_label,
                        state="pending", state_changed_at=None, state_changed_by=None,
                        last_failing_run=stored.run_id, last_failing_at=stored.created_at)
                    message = render_message(record, to=("x@example.test",),
                                             amounts=amounts_of(verdict),
                                             link=task_link(PUBLIC, record))
                    assert self._leaks(message, guest_details) == [], (control_id,
                                                                       verdict.record_id)
                    checked += 1
        assert checked > 500


# ---------------------------------------------------------------------------------------
class TestUnwiredIsTodaysDemoExactly:
    """No notifier, no change: the queue payload is byte-identical to slice 18's, which is
    what keeps every golden in fixtures/api/ unchanged (this slice may not touch them)."""

    def test_an_unwired_queue_names_no_delivery_at_all(self):
        app = App()
        run(app, CREDIT)
        listing = queue(app)
        assert "email" not in listing
        assert "delivery" not in listing["records"][0]

    def test_the_unwired_page_says_email_is_not_wired(self):
        app = App()
        page = text_of(app.handle("/queue?property=sandbox").body)
        assert "Email is not wired" in page

    def test_the_launcher_wires_no_notifier_unless_asked(self):
        from tools import serve

        assert serve.build_app("off").notifier is None
        assert serve.build_app("off", notify="off").notifier is None
