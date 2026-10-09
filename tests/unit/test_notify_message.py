# -*- coding: utf-8 -*-
"""
Slice 19 (G8 email): what an email about a task says, and when one is sent at all.

The engine holds a `Notifier` PROTOCOL and nothing that can reach a network: the SMTP backend
lives in `tools/notifiers/` and is injected, exactly as `tools/proposers/` is (D10). Everything
here runs against `RecordingNotifier`, which keeps messages in a list.

What is pinned, each against plan-v3 §5 slice 19:

  - an email carries a record id, the control, the amount WITH its currency, and a link - and
    nothing else from the evidence. Not the verdict's reason, which is built from field values
    and could quote any of them (criterion V6: no guest PII in an email);
  - one email per record per channel, however often dispatch runs: the sent marker lives on
    the record (slice 18's natural key carries the idempotency);
  - an audience with no route leaves the record unsent, SAYING "no route configured for
    audience finance". Never silently dropped;
  - a failed send releases the marker and says why, so the next dispatch can try again.
"""
from datetime import datetime, timedelta, timezone

import pytest

from hotelcontrols.actions import (DISMISSED, OPERATOR, ActionRecord, Finding, Findings,
                                   Message, NotifyFailed, amounts_of, dispatch, render_message,
                                   task_link)
from hotelcontrols.kernel import EvidenceLine, Money, Outcome, Value, Verdict
from hotelcontrols.runner import Run
from hotelcontrols.store import RunStore
from tools.notifiers import RecordingNotifier

TZ = timezone(timedelta(hours=3))
AT = datetime(2026, 7, 8, tzinfo=TZ)
SENT_AT = datetime(2026, 10, 9, 9, 30, tzinfo=TZ)
PUBLIC = "http://127.0.0.1:8765"


def credit_verdict(record_id="007004348", reason=None):
    return Verdict(Outcome.FAIL,
                   reason or "folio.balance_due is -490.75 ILS, which does not satisfy `gte 0`",
                   [EvidenceLine("folio.balance_due",
                                 Value.known(Money.parse("-490.75", "ILS"), source="pms:x/y")),
                    EvidenceLine("reservation.status",
                                 Value.known("checked_out", source="pms:x/z")),
                    EvidenceLine("reservation.guest.surname",
                                 Value.known("Almeida", source="pms:x/z"))],
                   control_id="checkout_unrefunded_credit", record_id=record_id)


def finding(record_id="007004348", audience="finance", kind="notify", tenant_id="sandbox"):
    """CONSTRUCTED - the real FAIL's shape, built here so a test can vary one part of it."""
    return Finding(tenant_id=tenant_id, control_id="checkout_unrefunded_credit",
                   control_name="Checkout With An Unrefunded Credit", policy_version=2,
                   policy_digest="sha256:fa15", record_id=record_id, severity="medium",
                   audience=audience, kind=kind, reason="folio.balance_due is -490.75 ILS",
                   run_id="run-1", raised_at=AT, as_of="2026-07-08", provider="constructed",
                   evidence_label="constructed")


def constructed_run(verdicts, run_id="run-1"):
    return Run(control_id="checkout_unrefunded_credit", control_name="Credit",
               natural_language="n.", tenant_id="sandbox", provider="constructed",
               evidence_label="constructed", evidence_is_synthetic=True, as_of="2026-07-08",
               created_at=AT, calls=0, verdicts=tuple(verdicts), run_id=run_id,
               policy_version=2, policy_digest="sha256:fa15")


def raised(store, *findings_):
    batch = Findings(run_id="run-1", tenant_id=findings_[0].tenant_id,
                     control_id="checkout_unrefunded_credit", policy_version=2, at=AT,
                     as_of="2026-07-08", failing=tuple(findings_))
    store.record_findings(batch)
    return batch


@pytest.fixture
def store():
    with RunStore() as opened:
        yield opened


@pytest.fixture
def finance():
    return RecordingNotifier({"finance": ("finance@example.test",)})


# ---------------------------------------------------------------------------------------
class TestWhatAnEmailCarries:

    def test_the_amount_travels_with_its_currency_and_nothing_else_from_the_evidence(self):
        """Money is the one evidence type that cannot carry a guest's details: a Decimal and
        three letters. A status, a name, a free-text remark - none of them is an amount."""
        assert amounts_of(credit_verdict()) == ("folio.balance_due -490.75 ILS",)

    def test_a_verdict_with_no_money_has_no_amount(self):
        verdict = Verdict(Outcome.FAIL, "r", [EvidenceLine(
            "room.type", Value.known("Executive", source="pms:x/y"))], record_id="r1")
        assert amounts_of(verdict) == ()

    def test_the_message_carries_record_control_amount_and_link(self, store):
        batch = raised(store, finding())
        record = store.action(batch.failing[0].action_id, tenant_id="sandbox")
        message = render_message(record, to=("finance@example.test",),
                                 amounts=amounts_of(credit_verdict()),
                                 link=task_link(PUBLIC, record))
        assert isinstance(message, Message)
        text = message.subject + "\n" + message.body
        for expected in ("007004348", "Checkout With An Unrefunded Credit",
                         "checkout_unrefunded_credit", "-490.75 ILS", "medium", "finance",
                         "%s/queue?property=sandbox#task-%s" % (PUBLIC, record.action_id)):
            assert expected in text, expected
        assert message.to == ("finance@example.test",)
        assert message.audience == "finance" and message.channel == "email"

    def test_the_verdicts_reason_never_reaches_the_message(self, store):
        """The reason is assembled from field values. Here it quotes a surname, as a reason over
        a guest field would - and the email must not repeat it."""
        batch = raised(store, finding())
        record = store.action(batch.failing[0].action_id, tenant_id="sandbox")
        message = render_message(record, to=("f@example.test",),
                                 amounts=amounts_of(credit_verdict(reason="surname is Almeida")),
                                 link=task_link(PUBLIC, record))
        assert "Almeida" not in message.subject + message.body
        assert record.reason not in message.body

    def test_the_message_says_it_is_advisory(self, store):
        """Nothing was changed anywhere: the engine never writes to a PMS (1.10)."""
        batch = raised(store, finding())
        record = store.action(batch.failing[0].action_id, tenant_id="sandbox")
        body = render_message(record, to=("f@example.test",), amounts=(),
                              link=task_link(PUBLIC, record)).body
        assert "advisory" in body.lower()


# ---------------------------------------------------------------------------------------
class TestOneEmailPerRecord:
    """Exit test 1: a FAIL emails its IR's audience once; a second dispatch sends nothing."""

    def test_a_new_task_is_emailed_to_its_audience_once(self, store, finance):
        batch = raised(store, finding())
        run = constructed_run([credit_verdict()])
        deliveries = dispatch(run, batch, store, finance, public_url=PUBLIC, at=SENT_AT)
        assert [d.outcome for d in deliveries] == ["sent"]
        (message,) = finance.sent
        assert message.to == ("finance@example.test",)
        record = store.action(batch.failing[0].action_id, tenant_id="sandbox")
        assert (record.notified_at, record.notified_via) == (SENT_AT, "email")

    def test_a_second_dispatch_sends_nothing(self, store, finance):
        batch = raised(store, finding())
        run = constructed_run([credit_verdict()])
        dispatch(run, batch, store, finance, public_url=PUBLIC, at=SENT_AT)
        again = dispatch(run, batch, store, finance, public_url=PUBLIC,
                         at=SENT_AT + timedelta(hours=1))
        assert len(finance.sent) == 1
        assert [d.outcome for d in again] == ["already_sent"]

    def test_a_closed_task_is_never_emailed(self, store, finance):
        """A person dismissed it before any route existed. Emailing it now would ask somebody
        to act on something already decided."""
        batch = raised(store, finding())
        store.transition(batch.failing[0].action_id, DISMISSED, tenant_id="sandbox",
                         at=SENT_AT, actor=OPERATOR)
        deliveries = dispatch(constructed_run([credit_verdict()]), batch, store, finance,
                              public_url=PUBLIC, at=SENT_AT)
        assert finance.sent == [] and [d.outcome for d in deliveries] == ["closed"]

    def test_only_a_notify_action_is_emailed(self, store, finance):
        """The IR schema allows `dashboard` and `report` actions. They raise a task and send
        nothing - a rule that asked for a dashboard did not ask for an email."""
        batch = raised(store, finding(kind="dashboard"))
        deliveries = dispatch(constructed_run([credit_verdict()]), batch, store, finance,
                              public_url=PUBLIC, at=SENT_AT)
        assert finance.sent == [] and [d.outcome for d in deliveries] == ["not_notify"]


# ---------------------------------------------------------------------------------------
class TestNothingIsSilentlyDropped:

    def test_an_audience_with_no_route_is_left_unsent_and_says_so(self, store):
        nobody = RecordingNotifier({})
        batch = raised(store, finding())
        deliveries = dispatch(constructed_run([credit_verdict()]), batch, store, nobody,
                              public_url=PUBLIC, at=SENT_AT)
        assert nobody.sent == []
        assert [d.outcome for d in deliveries] == ["no_route"]
        record = store.action(batch.failing[0].action_id, tenant_id="sandbox")
        assert record.notified_at is None
        assert record.notify_note == "no route configured for audience finance"
        assert record.state == "pending"

    def test_once_a_route_exists_the_next_dispatch_sends_it(self, store, finance):
        batch = raised(store, finding())
        run = constructed_run([credit_verdict()])
        dispatch(run, batch, store, RecordingNotifier({}), public_url=PUBLIC, at=SENT_AT)
        dispatch(run, batch, store, finance, public_url=PUBLIC, at=SENT_AT)
        assert len(finance.sent) == 1
        record = store.action(batch.failing[0].action_id, tenant_id="sandbox")
        assert record.notify_note is None and record.notified_at == SENT_AT

    def test_a_rule_with_no_audience_has_nobody_to_email_and_says_so(self, store, finance):
        batch = raised(store, finding(audience=None))
        deliveries = dispatch(constructed_run([credit_verdict()]), batch, store, finance,
                              public_url=PUBLIC, at=SENT_AT)
        assert finance.sent == [] and [d.outcome for d in deliveries] == ["no_audience"]
        record = store.action(batch.failing[0].action_id, tenant_id="sandbox")
        assert "names no audience" in record.notify_note

    def test_a_failed_send_releases_the_marker_and_says_why(self, store):
        broken = RecordingNotifier({"finance": ("f@example.test",)},
                                   fail=NotifyFailed("the mail server refused the connection"))
        batch = raised(store, finding())
        run = constructed_run([credit_verdict()])
        deliveries = dispatch(run, batch, store, broken, public_url=PUBLIC, at=SENT_AT)
        assert [d.outcome for d in deliveries] == ["failed"]
        record = store.action(batch.failing[0].action_id, tenant_id="sandbox")
        assert record.notified_at is None
        assert "refused the connection" in record.notify_note
        # And the next dispatch, with a working backend, sends it.
        working = RecordingNotifier({"finance": ("f@example.test",)})
        dispatch(run, batch, store, working, public_url=PUBLIC, at=SENT_AT)
        assert len(working.sent) == 1

    def test_an_unexpected_backend_error_is_not_swallowed(self, store):
        """Only a failure the backend NAMED is a delivery problem. Anything else is a defect,
        and a defect must surface rather than become a note on a task."""
        broken = RecordingNotifier({"finance": ("f@example.test",)}, fail=KeyError("bug"))
        batch = raised(store, finding())
        with pytest.raises(KeyError):
            dispatch(constructed_run([credit_verdict()]), batch, store, broken,
                     public_url=PUBLIC, at=SENT_AT)
        # The marker is released on the way out, so the task is not stuck as "sent".
        assert store.action(batch.failing[0].action_id, tenant_id="sandbox").notified_at is None


# ---------------------------------------------------------------------------------------
class TestTheMarkerIsScoped:
    """Criterion V4 on the new columns: the marker is written for a property, never across."""

    def test_claim_release_and_note_without_a_property_are_type_errors(self, store):
        batch = raised(store, finding())
        action_id = batch.failing[0].action_id
        with pytest.raises(TypeError):
            store.claim_notification(action_id, channel="email", at=SENT_AT)
        with pytest.raises(TypeError):
            store.release_notification(action_id, note="x")
        with pytest.raises(TypeError):
            store.note_notification(action_id, note="x")

    def test_another_property_cannot_claim_a_task(self, store):
        batch = raised(store, finding())
        action_id = batch.failing[0].action_id
        assert store.claim_notification(action_id, tenant_id="demo", channel="email",
                                        at=SENT_AT) is False
        assert store.claim_notification(action_id, tenant_id="sandbox", channel="email",
                                        at=SENT_AT) is True
        assert store.claim_notification(action_id, tenant_id="sandbox", channel="email",
                                        at=SENT_AT) is False

    def test_a_store_made_by_slice_18_gains_the_marker_columns(self, tmp_path):
        """slice 18's `actions` table has no marker columns, and CREATE TABLE IF NOT EXISTS
        will not add them - `_migrate` does, nullable, so an old task reads as never sent."""
        import sqlite3

        from hotelcontrols.store import sqlite as module

        path = tmp_path / "slice18.sqlite3"
        schema = module.SCHEMA.read_text(encoding="utf-8")
        for column in ("notified_at", "notified_via", "notify_note"):
            schema = "\n".join(line for line in schema.splitlines()
                               if not line.strip().startswith(column))
        connection = sqlite3.connect(path)
        connection.executescript(schema)
        connection.close()
        with RunStore(path) as opened:
            batch = raised(opened, finding())
            record = opened.action(batch.failing[0].action_id, tenant_id="sandbox")
            assert record.notified_at is None and record.notify_note is None
            assert opened.claim_notification(record.action_id, tenant_id="sandbox",
                                             channel="email", at=SENT_AT)


def test_an_action_record_reads_as_never_sent_by_default():
    record = ActionRecord(
        action_id="a", tenant_id="t", control_id="c", control_name="C", policy_version=2,
        policy_digest="d", record_id="r", severity="high", audience="finance", kind="notify",
        reason="x", raised_by_run="run", raised_at=AT, as_of="2026-07-08", provider="p",
        evidence_label="e", state="pending", state_changed_at=None, state_changed_by=None,
        last_failing_run="run", last_failing_at=AT)
    assert (record.notified_at, record.notified_via, record.notify_note) == (None, None, None)


def test_a_dispatch_that_loses_the_claim_to_another_sends_nothing(store, finance):
    """Two dispatches racing on one task: the second read the task before the first claimed
    it, so it still looks unsent - and the guarded claim is what stops a second email."""
    batch = raised(store, finding())
    action_id = batch.failing[0].action_id
    stale = store.action(action_id, tenant_id="sandbox")              # read: not yet sent
    assert store.claim_notification(action_id, tenant_id="sandbox", channel="email",
                                    at=SENT_AT)                         # the other one wins
    store.action = lambda aid, *, tenant_id: stale
    deliveries = dispatch(constructed_run([credit_verdict()]), batch, store, finance,
                          public_url=PUBLIC, at=SENT_AT)
    del store.action
    assert finance.sent == [] and [d.outcome for d in deliveries] == ["already_sent"]
