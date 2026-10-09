# -*- coding: utf-8 -*-
"""
Slice 18: the `actions` table - the findings queue, persisted, deduplicated and tenant-scoped.

Everything here runs on CONSTRUCTED findings: `Findings` objects built in this file, not runs
over a capture. They prove what the store does with a record, never a fact about the hotel. The
real FAIL (`checkout_unrefunded_credit` on 007004348) is in
`tests/integration/test_findings_queue.py`.

What is pinned, and what protects it:

  - one record per natural key however often it is offered (criterion V5, G10c), and a new
    policy version is a new record while the old one stays linked to its own version;
  - a later PASS ANNOTATES a record and never closes it; a person closes it (D12);
  - transitions are `pending -> done | dismissed`, stamped with the instant and the actor they
    are given (the clock is injected by the caller; `kernel/clock.py` is the only module that
    may read a wall clock);
  - every read names its property, keyword-only with no default, and another property's record
    is absent exactly like a record that never existed (criterion V4, slice 17's rule).
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from hotelcontrols.actions import (DISMISSED, DONE, OPERATOR, PENDING, Finding, Findings,
                                   TransitionRefused)
from hotelcontrols.store import RunStore

TZ = timezone(timedelta(hours=3))
DAY1 = datetime(2026, 7, 8, tzinfo=TZ)
DAY2 = DAY1 + timedelta(days=1)
DAY3 = DAY1 + timedelta(days=2)
LATER = datetime(2026, 10, 9, 9, 30, tzinfo=TZ)


def finding(record_id="R1", tenant_id="sandbox", policy_version=2, run_id="run-1", at=DAY1,
            control_id="checkout_money_owed", reason="folio.balance_due is 120.00 ILS"):
    """A CONSTRUCTED finding - a FAIL that no capture holds."""
    return Finding(tenant_id=tenant_id, control_id=control_id, control_name="Money owed",
                   policy_version=policy_version, policy_digest="sha256:%d" % policy_version,
                   record_id=record_id, severity="high", audience="finance", kind="notify",
                   reason=reason, run_id=run_id, raised_at=at, as_of=at.date().isoformat(),
                   provider="constructed", evidence_label="constructed")


def batch(failing=(), passing=(), run_id="run-1", at=DAY1, tenant_id="sandbox",
          policy_version=2, control_id="checkout_money_owed"):
    return Findings(run_id=run_id, tenant_id=tenant_id, control_id=control_id,
                    policy_version=policy_version, at=at, as_of=at.date().isoformat(),
                    failing=tuple(failing), passing=tuple(passing))


@pytest.fixture
def store():
    with RunStore() as opened:
        yield opened


# ---------------------------------------------------------------------------------------
class TestOneRecordPerNaturalKey:
    """Criterion V5: a FAIL creates exactly one pending record however often it is re-run."""

    def test_the_first_failure_creates_one_pending_record(self, store):
        created = store.record_findings(batch([finding()]))
        assert created == 1
        (record,) = store.actions(tenant_id="sandbox")
        assert record.state == PENDING
        assert (record.record_id, record.severity, record.audience) == ("R1", "high", "finance")
        assert record.raised_by_run == "run-1" and record.raised_at == DAY1
        assert record.state_changed_at is None and record.state_changed_by is None

    def test_offering_it_five_times_still_leaves_one(self, store):
        for _ in range(5):
            store.record_findings(batch([finding()]))
        assert len(store.actions(tenant_id="sandbox")) == 1

    def test_a_repeat_creates_none_and_says_so(self, store):
        assert store.record_findings(batch([finding()])) == 1
        assert store.record_findings(batch([finding()])) == 0

    def test_a_later_run_finding_it_again_keeps_the_record_and_notes_the_run(self, store):
        """The record is the same task; the newer run is the newer receipt."""
        store.record_findings(batch([finding()]))
        store.record_findings(batch([finding(run_id="run-2", at=DAY2, reason="95 ILS")],
                                    run_id="run-2", at=DAY2))
        (record,) = store.actions(tenant_id="sandbox")
        assert record.raised_by_run == "run-1"           # who raised it never changes
        assert record.reason == "folio.balance_due is 120.00 ILS"
        assert (record.last_failing_run, record.last_failing_at) == ("run-2", DAY2)

    def test_an_older_run_offered_late_does_not_rewind_the_receipt(self, store):
        store.record_findings(batch([finding(run_id="run-2", at=DAY2)], run_id="run-2", at=DAY2))
        store.record_findings(batch([finding()]))
        (record,) = store.actions(tenant_id="sandbox")
        assert record.last_failing_run == "run-2"

    def test_a_new_policy_version_judges_afresh_and_the_old_record_stays_on_v2(self, store):
        """plan-v3: 'A new policy version judges afresh and makes a new record, while the old
        one stays linked to v1.'"""
        store.record_findings(batch([finding()]))
        created = store.record_findings(batch([finding(policy_version=3, run_id="run-3",
                                                       at=DAY2)],
                                              run_id="run-3", at=DAY2, policy_version=3))
        assert created == 1
        records = store.actions(tenant_id="sandbox")
        assert sorted((r.policy_version, r.raised_by_run) for r in records) == [
            (2, "run-1"), (3, "run-3")]

    def test_two_records_in_one_run_are_two_records(self, store):
        assert store.record_findings(batch([finding("R1"), finding("R2")])) == 2


# ---------------------------------------------------------------------------------------
class TestALaterPassAnnotatesAndNeverCloses:
    """plan-v3: 'A later PASS annotates a pending record ("no longer failing as of run X"). It
    never closes it, because a person performs actions (D12).'"""

    def test_a_later_pass_annotates_the_record(self, store):
        store.record_findings(batch([finding()]))
        store.record_findings(batch(passing=["R1"], run_id="run-2", at=DAY2))
        (record,) = store.actions(tenant_id="sandbox")
        assert record.state == PENDING                   # never closed by a run
        assert (record.cleared_by_run, record.cleared_at) == ("run-2", DAY2)
        assert "no longer failing" in record.annotation.lower()
        assert "run-2" in record.annotation

    def test_a_pass_from_before_the_failure_annotates_nothing(self, store):
        store.record_findings(batch([finding(run_id="run-2", at=DAY2)], run_id="run-2", at=DAY2))
        store.record_findings(batch(passing=["R1"], run_id="run-1", at=DAY1))
        (record,) = store.actions(tenant_id="sandbox")
        assert record.cleared_by_run is None and record.annotation is None

    def test_a_pass_at_the_same_instant_as_the_failure_annotates_nothing(self, store):
        """A tie is not 'later'. The conservative reading is that it is still failing."""
        store.record_findings(batch([finding()]))
        store.record_findings(batch(passing=["R1"], run_id="run-x", at=DAY1))
        assert store.actions(tenant_id="sandbox")[0].cleared_by_run is None

    def test_failing_again_after_the_pass_removes_the_annotation(self, store):
        store.record_findings(batch([finding()]))
        store.record_findings(batch(passing=["R1"], run_id="run-2", at=DAY2))
        store.record_findings(batch([finding(run_id="run-3", at=DAY3)], run_id="run-3", at=DAY3))
        (record,) = store.actions(tenant_id="sandbox")
        assert record.cleared_by_run is None
        assert record.last_failing_run == "run-3"

    def test_a_pass_under_another_policy_version_annotates_nothing(self, store):
        """The record is a finding of ONE rule. A different rule passing the record says
        nothing about whether this one still fails."""
        store.record_findings(batch([finding()]))
        store.record_findings(batch(passing=["R1"], run_id="run-2", at=DAY2, policy_version=3))
        assert store.actions(tenant_id="sandbox")[0].cleared_by_run is None

    def test_a_pass_for_a_record_with_no_task_creates_nothing(self, store):
        assert store.record_findings(batch(passing=["R9"])) == 0
        assert store.actions(tenant_id="sandbox") == []


# ---------------------------------------------------------------------------------------
class TestTransitions:

    def test_marking_done_stamps_the_instant_and_the_actor_it_is_given(self, store):
        store.record_findings(batch([finding()]))
        (record,) = store.actions(tenant_id="sandbox")
        moved = store.transition(record.action_id, DONE, tenant_id="sandbox", at=LATER,
                                 actor=OPERATOR)
        assert (moved.state, moved.state_changed_at, moved.state_changed_by) == (
            DONE, LATER, "operator")
        assert store.action(record.action_id, tenant_id="sandbox") == moved

    def test_a_dismissed_record_cannot_be_marked_done(self, store):
        store.record_findings(batch([finding()]))
        action_id = store.actions(tenant_id="sandbox")[0].action_id
        store.transition(action_id, DISMISSED, tenant_id="sandbox", at=LATER, actor=OPERATOR)
        with pytest.raises(TransitionRefused):
            store.transition(action_id, DONE, tenant_id="sandbox", at=LATER, actor=OPERATOR)
        assert store.action(action_id, tenant_id="sandbox").state == DISMISSED

    def test_a_closed_record_is_not_reopened_by_failing_again(self, store):
        """A person closed it. A later FAIL updates the receipt and leaves their decision."""
        store.record_findings(batch([finding()]))
        action_id = store.actions(tenant_id="sandbox")[0].action_id
        store.transition(action_id, DONE, tenant_id="sandbox", at=LATER, actor=OPERATOR)
        assert store.record_findings(batch([finding(run_id="run-2", at=DAY2)],
                                           run_id="run-2", at=DAY2)) == 0
        record = store.action(action_id, tenant_id="sandbox")
        assert record.state == DONE and record.last_failing_run == "run-2"

    def test_an_absent_record_cannot_be_moved(self, store):
        assert store.transition("no-such-action", DONE, tenant_id="sandbox", at=LATER,
                                actor=OPERATOR) is None

    def test_a_naive_instant_is_refused(self, store):
        """The same rule as the clock: an instant with no zone is a guess."""
        store.record_findings(batch([finding()]))
        action_id = store.actions(tenant_id="sandbox")[0].action_id
        with pytest.raises(ValueError, match="timezone"):
            store.transition(action_id, DONE, tenant_id="sandbox",
                             at=datetime(2026, 10, 9, 9, 30), actor=OPERATOR)

    def test_an_actor_must_be_named(self, store):
        store.record_findings(batch([finding()]))
        action_id = store.actions(tenant_id="sandbox")[0].action_id
        with pytest.raises(ValueError, match="actor"):
            store.transition(action_id, DONE, tenant_id="sandbox", at=LATER, actor="")


# ---------------------------------------------------------------------------------------
class TestEveryReadNamesItsProperty:
    """Criterion V4 on the new table. The structural half - every statement scoped - is
    `tests/unit/test_tenant_scoped_store.py`, which discovers `actions` from schema.sql."""

    def test_reads_without_a_property_are_type_errors(self, store):
        store.record_findings(batch([finding()]))
        action_id = store.actions(tenant_id="sandbox")[0].action_id
        with pytest.raises(TypeError):
            store.actions()
        with pytest.raises(TypeError):
            store.action(action_id)
        with pytest.raises(TypeError):
            store.transition(action_id, DONE, at=LATER, actor=OPERATOR)
        with pytest.raises(TypeError):
            store.action(action_id, "sandbox")

    def test_another_propertys_record_is_absent(self, store):
        store.record_findings(batch([finding(tenant_id="sandbox")]))
        store.record_findings(batch([finding(tenant_id="demo")], tenant_id="demo"))
        sandbox = store.actions(tenant_id="sandbox")
        demo = store.actions(tenant_id="demo")
        assert [r.tenant_id for r in sandbox] == ["sandbox"]
        assert [r.tenant_id for r in demo] == ["demo"]
        assert store.action(sandbox[0].action_id, tenant_id="demo") is None

    def test_another_property_cannot_move_a_record(self, store):
        store.record_findings(batch([finding(tenant_id="sandbox")]))
        action_id = store.actions(tenant_id="sandbox")[0].action_id
        assert store.transition(action_id, DONE, tenant_id="demo", at=LATER,
                                actor=OPERATOR) is None
        assert store.action(action_id, tenant_id="sandbox").state == PENDING

    def test_a_pass_in_one_property_annotates_nothing_in_another(self, store):
        store.record_findings(batch([finding(tenant_id="sandbox")]))
        store.record_findings(batch(passing=["R1"], run_id="run-2", at=DAY2, tenant_id="demo"))
        assert store.actions(tenant_id="sandbox")[0].cleared_by_run is None

    def test_a_findings_batch_whose_records_name_another_property_is_refused(self, store):
        """A batch is one run's, for one property. A record inside it claiming another
        property would be written into the wrong hotel's queue."""
        with pytest.raises(ValueError, match="property"):
            store.record_findings(batch([finding(tenant_id="demo")], tenant_id="sandbox"))
        assert store.actions(tenant_id="demo") == []


# ---------------------------------------------------------------------------------------
class TestOrderAndPersistence:

    def test_pending_comes_first_then_by_severity(self, store):
        store.record_findings(batch([finding("R1"), finding("R2")]))
        medium = replace(finding("R3", control_id="checkout_unrefunded_credit"),
                         severity="medium")
        store.record_findings(batch([medium], control_id="checkout_unrefunded_credit"))
        first = store.actions(tenant_id="sandbox")[0].action_id
        store.transition(first, DONE, tenant_id="sandbox", at=LATER, actor=OPERATOR)
        states = [(r.state, r.severity) for r in store.actions(tenant_id="sandbox")]
        assert states == [(PENDING, "high"), (PENDING, "medium"), (DONE, "high")]

    def test_a_file_store_keeps_the_queue_across_a_restart(self, tmp_path):
        """The demo's default store is in memory and the queue page says so. A file store is
        the opt-in `--store PATH`, and what it promises is this."""
        path = tmp_path / "queue.sqlite3"
        with RunStore(path) as first:
            first.record_findings(batch([finding()]))
            action_id = first.actions(tenant_id="sandbox")[0].action_id
            first.transition(action_id, DONE, tenant_id="sandbox", at=LATER, actor=OPERATOR)
            assert first.persistent
        with RunStore(path) as reopened:
            record = reopened.action(action_id, tenant_id="sandbox")
            assert record.state == DONE and record.state_changed_at == LATER
            assert reopened.record_findings(batch([finding()])) == 0

    def test_an_in_memory_store_says_it_is_not_persistent(self, store):
        assert store.persistent is False

    def test_a_database_made_before_this_slice_gains_the_table(self, tmp_path):
        """`CREATE TABLE IF NOT EXISTS` adds a table to an old file, so a store written by
        slice 17 opens and queues without a manual step."""
        import sqlite3
        path = tmp_path / "old.sqlite3"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, control_id TEXT NOT "
                           "NULL, control_name TEXT NOT NULL, natural_language TEXT NOT NULL, "
                           "tenant_id TEXT NOT NULL, provider TEXT NOT NULL, evidence_label "
                           "TEXT NOT NULL, evidence_is_synthetic INTEGER NOT NULL, as_of TEXT "
                           "NOT NULL, created_at TEXT NOT NULL, calls INTEGER NOT NULL, "
                           "blocked TEXT)")
        connection.commit()
        connection.close()
        with RunStore(path) as opened:
            assert opened.record_findings(batch([finding()])) == 1


class TestAMoveRacingAnotherWriter:
    """The UPDATE carries `AND state = 'pending'`, so a task closed by another writer between
    the read and the write - a second process on the same file store - is refused rather than
    overwritten. Simulated by handing `transition` a stale read."""

    def test_a_task_closed_between_the_read_and_the_write_is_refused(self, store):
        store.record_findings(batch([finding()]))
        action_id = store.actions(tenant_id="sandbox")[0].action_id
        stale = store.action(action_id, tenant_id="sandbox")         # still says pending
        store.transition(action_id, DISMISSED, tenant_id="sandbox", at=LATER, actor="other")
        reads = iter([stale])
        real = store.action
        store.action = lambda aid, *, tenant_id: next(reads, None) or real(aid, tenant_id=tenant_id)
        with pytest.raises(TransitionRefused):
            store.transition(action_id, DONE, tenant_id="sandbox", at=LATER, actor=OPERATOR)
        del store.action
        record = store.action(action_id, tenant_id="sandbox")
        assert (record.state, record.state_changed_by) == (DISMISSED, "other")
