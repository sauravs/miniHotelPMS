# -*- coding: utf-8 -*-
"""
Slice 18 (G2(a), G8 queue, G10c): the pure half of the findings queue.

`hotelcontrols/actions/` turns ONE RUN into action records using the IR's own `action` block -
severity and audience, carried by every control since slice 1 and read by nothing until now.
No new configuration is invented for it (plan-v3 §5, slice 18).

What this file pins, each against the plan rather than the code:

  - only a FAIL makes a record. UNKNOWN does not, because whether UNKNOWNs become a review
    queue is open question 1.1 and this slice must not answer it by accident. EXCLUDED does not.
    A blocked run and a run that concluded nothing make nothing (criterion V5, brief §8.5);
  - severity and audience come STRAIGHT FROM THE IR, and an IR that declares no audience gets
    none - never a plausible default;
  - the record's identity is its NATURAL KEY - property, control, policy version, record - and
    nothing else, so a repeated run cannot make a second record and `make_run_id` stays
    untouched (plan-v3 §6.6, G10c);
  - states go `pending -> done | dismissed`, and nothing else.

ON ISSUE #59. The plan's exit test 1 named `checkout_money_owed`, which has no FAIL on any
capture, so it would have passed with zero records. Its high/finance mapping is therefore proven
HERE, on a CONSTRUCTED run - a Run object built in this file, not evidence, and labelled as such
wherever it is used. The mapping on real evidence is proven on `checkout_unrefunded_credit`'s one
real FAIL in `tests/integration/test_findings_queue.py`.
"""
import copy
from datetime import datetime, timedelta, timezone

import pytest

from hotelcontrols.actions import (DISMISSED, DONE, OPERATOR, PENDING, STATES, Finding,
                                   TransitionRefused, action_id_for, check_transition,
                                   findings_from)
from hotelcontrols.kernel import EvidenceLine, Money, Outcome, Value, Verdict
from hotelcontrols.runner import Run
from hotelcontrols.spec import ControlIR, load

AT = datetime(2026, 7, 8, tzinfo=timezone(timedelta(hours=3)))


def verdict(outcome, record_id, control_id="checkout_money_owed", reason=None):
    return Verdict(outcome, reason or "%s for %s" % (outcome.value, record_id),
                   [EvidenceLine("folio.balance_due",
                                 Value.known(Money.parse("120.00", "ILS"), source="pms:x/y"))],
                   control_id=control_id, record_id=record_id)


def constructed_run(ir, verdicts=(), blocked=None, run_id="run-1", tenant_id="sandbox",
                    created_at=AT, policy_version="ir", policy_digest="ir"):
    """A CONSTRUCTED Run: built here, from no capture. It proves a mapping, never a fact about
    the hotel. Named 'constructed' everywhere it is used, because issue #59 is what happens when
    a test claims more than its evidence holds."""
    return Run(control_id=ir.control_id, control_name=ir.name,
               natural_language=ir.natural_language, tenant_id=tenant_id,
               provider="constructed", evidence_label="constructed", evidence_is_synthetic=True,
               as_of=created_at.date().isoformat(), created_at=created_at, calls=0,
               verdicts=tuple(verdicts), blocked=blocked, run_id=run_id, maximum_age="1h",
               policy_version=ir.version if policy_version == "ir" else policy_version,
               policy_digest=ir.digest if policy_digest == "ir" else policy_digest)


@pytest.fixture(scope="module")
def money_owed():
    return load("checkout_money_owed")


@pytest.fixture(scope="module")
def unrefunded():
    return load("checkout_unrefunded_credit")


# ---------------------------------------------------------------------------------------
class TestTheMappingComesStraightFromTheIR:
    """plan-v3 §5 slice 18: "using the IR's own action block ... No new configuration is
    invented for it." """

    def test_constructed_run_money_owed_fail_is_high_and_finance(self, money_owed):
        """#59: CONSTRUCTED - no capture holds a money-owed FAIL (0 FAIL at every instant in
        July 2026). This proves the mapping, and only the mapping."""
        run = constructed_run(money_owed, [verdict(Outcome.FAIL, "R-CONSTRUCTED")])
        found = findings_from(run, money_owed)

        assert [f.record_id for f in found.failing] == ["R-CONSTRUCTED"]
        record = found.failing[0]
        assert (record.severity, record.audience, record.kind) == ("high", "finance", "notify")
        # Straight from the IR, not from a table here that happens to agree with it today.
        assert record.severity == money_owed["action"]["severity"]
        assert record.audience == money_owed["action"]["audience"]
        assert record.kind == money_owed["action"]["type"]

    def test_unrefunded_credit_maps_to_medium_and_finance(self, unrefunded):
        run = constructed_run(unrefunded, [verdict(Outcome.FAIL, "007004348",
                                                   "checkout_unrefunded_credit")])
        (record,) = findings_from(run, unrefunded).failing
        assert (record.severity, record.audience) == ("medium", "finance")

    def test_the_record_carries_the_rule_and_the_run_that_raised_it(self, money_owed):
        """Every record v3 creates names the policy version that produced it (plan-v3 §4,
        'Why the sequence'), and links to the run whose evidence is its receipt."""
        run = constructed_run(money_owed, [verdict(Outcome.FAIL, "R1",
                                                   reason="folio.balance_due is 120.00 ILS")])
        (record,) = findings_from(run, money_owed).failing
        assert record.policy_version == money_owed.version == 2
        assert record.policy_digest == money_owed.digest
        assert record.run_id == "run-1"
        assert record.raised_at == AT
        assert record.tenant_id == "sandbox"
        assert record.control_name == money_owed.name
        # The verdict's own reason, which already carries the amount WITH its currency (R9).
        assert record.reason == "folio.balance_due is 120.00 ILS"

    def test_an_ir_that_declares_no_audience_gets_none_not_a_default(self, money_owed):
        """The schema makes `audience` optional. A record for nobody in particular says so;
        inventing "front office" would route a finance problem to the wrong desk."""
        raw = copy.deepcopy(money_owed.raw)
        del raw["action"]["audience"]
        silent = ControlIR(raw)
        run = constructed_run(silent, [verdict(Outcome.FAIL, "R1")])
        (record,) = findings_from(run, silent).failing
        assert record.audience is None


# ---------------------------------------------------------------------------------------
class TestOnlyAFailMakesARecord:
    """Criterion V5, and open question 1.1 left open on purpose."""

    @pytest.mark.parametrize("outcome", [Outcome.UNKNOWN, Outcome.EXCLUDED])
    def test_unknown_and_excluded_make_no_record(self, money_owed, outcome):
        run = constructed_run(money_owed, [verdict(Outcome.PASS, "P"),
                                           verdict(outcome, "X")])
        found = findings_from(run, money_owed)
        assert found.failing == ()
        assert "X" not in found.passing

    def test_a_pass_makes_no_record_but_is_reported_so_it_can_annotate_one(self, money_owed):
        """plan-v3: a later PASS ANNOTATES a pending record. It never creates or closes one."""
        run = constructed_run(money_owed, [verdict(Outcome.PASS, "P1"),
                                           verdict(Outcome.FAIL, "F1"),
                                           verdict(Outcome.PASS, "P2")])
        found = findings_from(run, money_owed)
        assert [f.record_id for f in found.failing] == ["F1"]
        assert found.passing == ("P1", "P2")

    def test_a_blocked_run_makes_nothing(self, money_owed):
        """Brief §8.5: a run that could not happen notifies nobody."""
        run = constructed_run(money_owed, blocked="the evidence was not in this capture")
        found = findings_from(run, money_owed)
        assert found.failing == () and found.passing == ()

    @pytest.mark.parametrize("outcomes", [
        (Outcome.EXCLUDED,) * 28,                       # ooo_room_protection's shape
        (Outcome.UNKNOWN,) * 37 + (Outcome.EXCLUDED,) * 71,   # required_reservation_fields'
        (),                                             # an empty population
    ], ids=["all-excluded", "unknown-and-excluded", "empty"])
    def test_a_run_that_concluded_nothing_makes_nothing(self, money_owed, outcomes):
        run = constructed_run(money_owed, [verdict(o, "r%d" % i) for i, o in enumerate(outcomes)])
        assert not run.coverage.concluded
        found = findings_from(run, money_owed)
        assert found.failing == () and found.passing == ()


# ---------------------------------------------------------------------------------------
class TestARecordCannotBeAttachedToTheWrongRule:
    """A record names the rule that judged it. If the IR handed in is not that rule, its
    severity and audience are somebody else's, and the record would be a misattribution."""

    def test_another_controls_ir_is_refused(self, money_owed, unrefunded):
        run = constructed_run(money_owed, [verdict(Outcome.FAIL, "R1")])
        with pytest.raises(ValueError, match="checkout_unrefunded_credit"):
            findings_from(run, unrefunded)

    def test_a_run_judged_under_another_version_is_refused(self, money_owed):
        run = constructed_run(money_owed, [verdict(Outcome.FAIL, "R1")], policy_version=3)
        with pytest.raises(ValueError, match="version"):
            findings_from(run, money_owed)

    def test_a_run_judged_under_another_digest_is_refused(self, money_owed):
        """A rule edited without its bump: same version, different content (slice 16)."""
        run = constructed_run(money_owed, [verdict(Outcome.FAIL, "R1")],
                              policy_digest="sha256:" + "0" * 64)
        with pytest.raises(ValueError, match="digest"):
            findings_from(run, money_owed)

    def test_a_run_that_cannot_name_its_rule_makes_no_record(self, money_owed):
        """A run stored before slice 16 reads 'version not recorded'. A task raised from it
        could not say which rule it enforces, so none is raised."""
        run = constructed_run(money_owed, [verdict(Outcome.FAIL, "R1")],
                              policy_version=None, policy_digest=None)
        with pytest.raises(ValueError, match="version"):
            findings_from(run, money_owed)

    def test_an_unsaved_run_is_refused(self, money_owed):
        """The record links to the run that is its receipt. With no run id there is none."""
        run = constructed_run(money_owed, [verdict(Outcome.FAIL, "R1")], run_id=None)
        with pytest.raises(ValueError, match="run id"):
            findings_from(run, money_owed)

    def test_a_fail_with_no_record_id_is_refused_rather_than_merged(self, money_owed):
        """Two FAILs with no id would share one natural key and collapse into one record - a
        violation silently dropped. Refused loudly instead."""
        run = constructed_run(money_owed, [verdict(Outcome.FAIL, None)])
        with pytest.raises(ValueError, match="record id"):
            findings_from(run, money_owed)


# ---------------------------------------------------------------------------------------
class TestIdentityIsTheNaturalKey:
    """G10c, narrowed: idempotency lives on the record, and `make_run_id` is untouched."""

    def test_the_same_failure_in_two_runs_has_one_identity(self, money_owed):
        first = constructed_run(money_owed, [verdict(Outcome.FAIL, "R1", reason="120 ILS")],
                                run_id="run-a")
        later = constructed_run(money_owed, [verdict(Outcome.FAIL, "R1", reason="95 ILS")],
                                run_id="run-b", created_at=AT + timedelta(days=1))
        (a,) = findings_from(first, money_owed).failing
        (b,) = findings_from(later, money_owed).failing
        assert a.key == b.key == ("sandbox", "checkout_money_owed", 2, "R1")
        assert a.action_id == b.action_id

    @pytest.mark.parametrize("change", [
        {"tenant_id": "demo"}, {"control_id": "checkout_unrefunded_credit"},
        {"policy_version": 3}, {"record_id": "R2"},
    ])
    def test_each_part_of_the_key_changes_the_identity(self, change):
        key = dict(tenant_id="sandbox", control_id="checkout_money_owed", policy_version=2,
                   record_id="R1")
        assert action_id_for(**key) != action_id_for(**{**key, **change})

    def test_the_identity_is_stable_across_processes(self):
        """A digest of the key, not `hash()`, which Python salts per process - so a file store
        reopened tomorrow still finds the record it made today."""
        assert action_id_for(tenant_id="sandbox", control_id="c", policy_version=2,
                             record_id="R1") == action_id_for(
            tenant_id="sandbox", control_id="c", policy_version=2, record_id="R1")
        assert len(action_id_for(tenant_id="s", control_id="c", policy_version=1,
                                 record_id="r")) == 16

    def test_a_finding_is_its_own_value(self, money_owed):
        run = constructed_run(money_owed, [verdict(Outcome.FAIL, "R1")])
        (record,) = findings_from(run, money_owed).failing
        assert isinstance(record, Finding)
        with pytest.raises(AttributeError):
            record.severity = "low"


# ---------------------------------------------------------------------------------------
class TestStates:
    """plan-v3: `pending -> done | dismissed`. A person performs actions (D12), so there is no
    state a run can move a record into, and nothing re-opens a closed one."""

    def test_the_three_states(self):
        assert STATES == (PENDING, DONE, DISMISSED) == ("pending", "done", "dismissed")

    @pytest.mark.parametrize("target", [DONE, DISMISSED])
    def test_a_pending_record_can_be_marked_done_or_dismissed(self, target):
        check_transition(PENDING, target)          # does not raise

    @pytest.mark.parametrize("current, target", [
        (DONE, PENDING), (DONE, DISMISSED), (DISMISSED, DONE), (DISMISSED, PENDING),
        (PENDING, PENDING), (DONE, DONE),
    ])
    def test_every_other_move_is_refused(self, current, target):
        with pytest.raises(TransitionRefused):
            check_transition(current, target)

    @pytest.mark.parametrize("target", ["closed", "resolved", "", "PENDING"])
    def test_a_state_that_does_not_exist_is_not_a_transition(self, target):
        with pytest.raises(ValueError, match="state"):
            check_transition(PENDING, target)

    def test_the_actor_until_slice_24_is_the_operator(self):
        """No identity exists before slice 24's signed context, so the actor is named for
        what it is rather than for a person nobody authenticated."""
        assert OPERATOR == "operator"
