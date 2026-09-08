# -*- coding: utf-8 -*-
"""
Run history, and what must survive a round trip.

A verdict that cannot be re-read is not an audit trail. The store exists so a result can be
looked at again WITHOUT re-querying the PMS - which matters more than it sounds, because a folio
costs one call per reservation (R1) and re-running to answer "what did it say?" is the expensive
mistake this prevents.

THE THING THAT MUST NOT BE LOST is the evidence table exactly as it was: the value, its unit,
whether it was known, the reason it was not, the risk id, and the provenance. A stored FAIL with
the number missing is an accusation without a receipt.
"""
from datetime import datetime
from decimal import Decimal

import pytest

from hotelcontrols.kernel import NOT_APPLICABLE, EvidenceLine, Money, Outcome, Value, Verdict
from hotelcontrols.runner import Run
from hotelcontrols.store import RunStore, decode_payload, encode_payload


def a_run(control_id="checkout_money_owed", verdicts=(), blocked=None, created_at=None):
    return Run(
        control_id=control_id, control_name="Checkout With Money Owed",
        natural_language="A reservation cannot be closed while the guest still owes money.",
        tenant_id="sandbox", provider="minihotel", evidence_label="sandbox2026",
        evidence_is_synthetic=False, as_of="2026-07-08",
        created_at=created_at or datetime(2026, 9, 8, 12, 0, 0), calls=3,
        verdicts=tuple(verdicts), blocked=blocked)


@pytest.fixture
def store():
    with RunStore() as s:
        yield s


class TestPayloadEncoding:
    def test_money_survives_with_its_currency(self):
        """R9. An amount that came back as a bare number would have lost the half that makes
        it evidence."""
        restored = decode_payload(encode_payload(Money(Decimal("-490.75"), "ILS")))
        assert restored == Money(Decimal("-490.75"), "ILS")
        assert isinstance(restored.amount, Decimal)

    def test_the_not_applicable_sentinel_survives_as_itself(self):
        """R7. 'There is no channel confirmation because this was a direct booking' must
        survive as that - written as null or "" it becomes an evidence gap, and every direct
        booking looks like a duplicate of every other one again."""
        assert decode_payload(encode_payload(NOT_APPLICABLE)) is NOT_APPLICABLE

    def test_a_set_reference_survives_as_a_tuple(self):
        assert decode_payload(encode_payload(("dbl", "twin"))) == ("dbl", "twin")

    def test_ordinary_values_survive(self):
        for payload in ("checked_out", 3, True, False, "2026-07-08"):
            assert decode_payload(encode_payload(payload)) == payload


class TestRoundTrip:
    def test_a_run_comes_back_with_everything_it_went_in_with(self, store):
        original = a_run(verdicts=[Verdict(
            Outcome.FAIL, "folio.balance_due is -490.75 ILS, which does not satisfy `gte 0`",
            [EvidenceLine("folio.balance_due",
                          Value.known(Money(Decimal("-490.75"), "ILS"),
                                      source="pms:minihotel/GetReservationBalance"))],
            control_id="checkout_unrefunded_credit", record_id="007004348")])
        restored = store.load(store.save(original))

        assert restored.control_id == original.control_id
        assert restored.natural_language == original.natural_language
        assert restored.calls == 3
        assert restored.counts == original.counts
        assert restored.verdicts[0].outcome is Outcome.FAIL
        assert restored.verdicts[0].record_id == "007004348"

    def test_the_evidence_table_survives_intact(self, store):
        """Value, unit, provenance - all of it, or a stored FAIL is an accusation with no
        receipt."""
        original = a_run(verdicts=[Verdict(
            Outcome.FAIL, "a reason",
            [EvidenceLine("folio.balance_due",
                          Value.known(Money(Decimal("-490.75"), "ILS"),
                                      source="pms:minihotel/GetReservationBalance"))],
            record_id="007004348")])
        line = store.load(store.save(original)).verdicts[0].evidence[0]
        assert line.field == "folio.balance_due"
        assert line.value.payload == Money(Decimal("-490.75"), "ILS")
        assert line.value.unit == "ILS"
        assert line.source == "pms:minihotel/GetReservationBalance"

    def test_an_unknown_keeps_its_reason_and_risk_id(self, store):
        """An UNKNOWN without its reason cannot tell a hotel what to fix, which is the whole
        commercial value of the state."""
        original = a_run(verdicts=[Verdict(
            Outcome.UNKNOWN, "balance not established",
            [EvidenceLine("folio.balance_due",
                          Value.unknown("the response could not be fetched", risk="R1",
                                        source="pms:minihotel/GetReservationBalance"))],
            record_id="007004365")])
        line = store.load(store.save(original)).verdicts[0].evidence[0]
        assert line.value.is_known is False
        assert line.value.reason == "the response could not be fetched"
        assert line.value.risk == "R1"

    def test_a_blocked_run_round_trips_with_its_reason_and_no_verdicts(self, store):
        restored = store.load(store.save(a_run(blocked="the call budget stopped this run")))
        assert restored.is_blocked
        assert restored.blocked == "the call budget stopped this run"
        assert restored.verdicts == ()

    def test_an_unknown_run_id_returns_none_rather_than_raising(self, store):
        assert store.load("no-such-run") is None


class TestHistory:
    def test_runs_are_listed_newest_first(self, store):
        for day in (1, 3, 2):
            store.save(a_run(created_at=datetime(2026, 9, day, 12, 0)))
        dates = [row["created_at"] for row in store.history()]
        assert dates == sorted(dates, reverse=True)

    def test_history_can_be_narrowed_to_one_control(self, store):
        store.save(a_run("checkout_money_owed", created_at=datetime(2026, 9, 1)))
        store.save(a_run("checkout_unrefunded_credit", created_at=datetime(2026, 9, 2)))
        rows = store.history("checkout_money_owed")
        assert len(rows) == 1 and rows[0]["control_id"] == "checkout_money_owed"

    def test_history_carries_the_counts_so_a_trend_needs_no_second_query(self, store):
        store.save(a_run(verdicts=[
            Verdict(Outcome.PASS, "r", [EvidenceLine("f", Value.known("v"))]),
            Verdict(Outcome.FAIL, "r", [EvidenceLine("f", Value.known("v"))])]))
        row = store.history()[0]
        assert (row["passes"], row["fails"], row["total"]) == (1, 1, 2)

    def test_re_reading_a_run_spends_no_provider_calls(self, store):
        """R1, and the reason the store exists at all. Re-running to answer 'what did it say?'
        would cost one call per reservation all over again."""
        run_id = store.save(a_run(verdicts=[
            Verdict(Outcome.PASS, "r", [EvidenceLine("f", Value.known("v"))])]))
        restored = store.load(run_id)
        assert restored.calls == 3, "the stored call count is a record, not a new cost"


class TestSchema:
    def test_a_fresh_database_needs_no_setup_step(self, tmp_path):
        """An empty file becomes a valid database on first open. A demo that needs a migration
        command has lost the plot."""
        path = tmp_path / "runs.sqlite3"
        with RunStore(path) as store:
            assert store.save(a_run())
        assert path.exists()

    def test_reopening_an_existing_database_does_not_destroy_it(self, tmp_path):
        path = tmp_path / "runs.sqlite3"
        with RunStore(path) as store:
            run_id = store.save(a_run())
        with RunStore(path) as store:
            assert store.load(run_id) is not None

    def test_saving_the_same_run_twice_replaces_rather_than_duplicates(self, store):
        run = a_run(verdicts=[Verdict(Outcome.PASS, "r",
                                      [EvidenceLine("f", Value.known("v"))])])
        first, second = store.save(run), store.save(run)
        assert first == second
        assert len(store.history()) == 1
