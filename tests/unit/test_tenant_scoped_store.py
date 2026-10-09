# -*- coding: utf-8 -*-
"""
Slice 17 (G5, the data half): one property can no longer read another property's results.

Until now `tenant_id` was stored on every run and filtered by nothing: `load` read by run id,
`history` by control id, and a second property's runs sat in the same list as the first's
(plan-v3 §2). One missed `WHERE` in a multi-property store is not a bug, it is a breach - so
this slice makes the predicate impossible to forget rather than easy to remember:

  - every read takes the property as a KEYWORD-ONLY argument with NO DEFAULT. A call without
    one is a `TypeError` at the call site, not a query that quietly returns everything
    (D3 §80: fail loudly);
  - another property's run reads as ABSENT - `None`, which the web layer turns into a 404, not
    a 403 - so a run id cannot even be probed for existence;
  - a STRUCTURAL test, in the style of the canonical-boundary grep, reads every SQL statement in
    `store/` and fails one that touches a tenant-owned table without a bound tenant predicate.
    The tables are discovered from `schema.sql`, so every table v3 adds later (actions,
    decisions) is covered the day it is created. That is the reason to take this slice early.

Every test protects criterion V4 (plan-v3 §7) unless it names another.
"""
import ast
import pathlib
import re
from datetime import datetime, timezone

import pytest

from hotelcontrols.kernel import EvidenceLine, Money, Outcome, Value, Verdict
from hotelcontrols.runner import Run
from hotelcontrols.store import RunStore

STORE = pathlib.Path(__file__).resolve().parents[2] / "hotelcontrols" / "store"

# Tables in `schema.sql` that are NOT owned by a property. Empty, and it should stay empty: a
# table added here is a table one property's data can leak through. Adding one is a decision to
# show the owner, not a convenience.
NOT_TENANT_OWNED: frozenset[str] = frozenset()


def a_run(tenant_id="sandbox", control_id="checkout_money_owed", hour=12, run_id=None):
    verdict = Verdict(Outcome.FAIL, "money owed",
                      [EvidenceLine("folio.balance_due",
                                    Value.known(Money.parse("100", "ILS"), source="pms:x/y"))],
                      control_id=control_id, record_id="r-%s" % tenant_id)
    return Run(control_id=control_id, control_name="C", natural_language="n.",
               tenant_id=tenant_id, provider="minihotel", evidence_label="cap",
               evidence_is_synthetic=False, as_of="2026-07-08",
               created_at=datetime(2026, 7, 8, hour), calls=2, verdicts=(verdict,),
               maximum_age="1h", run_id=run_id, policy_version=2, policy_digest="sha256:x")


@pytest.fixture
def two_properties():
    """One store holding a run for each of two properties - the shape of every leak."""
    store = RunStore()
    a = store.save(a_run("demo", hour=10))
    b = store.save(a_run("sandbox", hour=11))
    yield store, a, b
    store.close()


# --------------------------------------------------------------------------- the API
class TestEveryReadNamesItsProperty:

    def test_load_without_a_property_is_a_type_error(self, two_properties):
        store, a, _b = two_properties
        with pytest.raises(TypeError):
            store.load(a)

    def test_history_without_a_property_is_a_type_error(self, two_properties):
        store, _a, _b = two_properties
        with pytest.raises(TypeError):
            store.history()
        with pytest.raises(TypeError):
            store.history("checkout_money_owed")

    def test_the_property_cannot_be_passed_by_position(self, two_properties):
        """Keyword-only, so `history("checkout_money_owed", "demo")` cannot be misread as a
        limit or a control id - and so a reader of the call site can see the property."""
        store, a, _b = two_properties
        with pytest.raises(TypeError):
            store.load(a, "demo")


class TestAnotherPropertysRunIsAbsent:

    def test_a_property_reads_its_own_run(self, two_properties):
        store, a, b = two_properties
        assert store.load(a, tenant_id="demo").tenant_id == "demo"
        assert store.load(b, tenant_id="sandbox").tenant_id == "sandbox"

    def test_another_propertys_run_is_none_exactly_like_a_run_that_does_not_exist(
            self, two_properties):
        """Not an error, not a "forbidden": absent. A 403 would confirm the id exists."""
        store, a, _b = two_properties
        assert store.load(a, tenant_id="sandbox") is None
        assert store.load("no-such-run", tenant_id="sandbox") is None

    def test_history_lists_only_the_propertys_own_runs(self, two_properties):
        store, a, b = two_properties
        assert [row["run_id"] for row in store.history(tenant_id="demo")] == [a]
        assert [row["run_id"] for row in store.history("checkout_money_owed",
                                                       tenant_id="sandbox")] == [b]

    def test_a_property_with_no_runs_has_an_empty_history(self, two_properties):
        store, _a, _b = two_properties
        assert store.history(tenant_id="a-third-hotel") == []

    def test_a_save_cannot_overwrite_another_propertys_run(self, two_properties):
        """Run ids hash the property, so two properties' ids cannot collide by accident. A run
        that arrives carrying another property's id anyway is refused rather than replacing
        that property's verdicts - INSERT OR REPLACE would have done exactly that."""
        store, a, _b = two_properties
        with pytest.raises(ValueError, match="another property"):
            store.save(a_run("sandbox", run_id=a))
        survivor = store.load(a, tenant_id="demo")
        assert survivor is not None and survivor.verdicts[0].record_id == "r-demo"


# --------------------------------------------------------------------------- structural
def tenant_owned_tables() -> frozenset[str]:
    """Every table `schema.sql` creates, minus the declared exceptions (there are none)."""
    sql = (STORE / "schema.sql").read_text(encoding="utf-8")
    return frozenset(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", sql)) - NOT_TENANT_OWNED


_VERB = re.compile(r"^\s*(SELECT|UPDATE|DELETE|WITH)\b", re.I)
_TABLE = re.compile(r"\b(?:FROM|JOIN|UPDATE)\s+(\w+)", re.I)
# A tenant predicate BOUND to a value by EQUALITY: `tenant_id = ?`, `r.tenant_id = :tenant`, or -
# as SQLite hands a trace callback the expanded statement - `tenant_id = 'sandbox'`. Naming the
# column in a SET clause or a SELECT list is not a predicate, and `tenant_id != ?` is the opposite
# of one: it selects every OTHER property's rows.
_PREDICATE = re.compile(r"\b(?:\w+\.)?tenant_id\s*=\s*(?:\?|:\w+|'[^']*')", re.I)


def unscoped(statement: str, owned: frozenset[str]) -> list[str]:
    """The tenant-owned tables a read, update or delete touches with no tenant predicate.

    Pure, so the rule itself is tested below - a structural test that can never fail is a
    comment with a green tick.
    """
    if not _VERB.match(statement):
        return []
    touched = sorted({t.lower() for t in _TABLE.findall(statement)} & owned)
    # Only a predicate AFTER the first WHERE filters anything: `SET tenant_id = ?` and a
    # `SELECT tenant_id` list both name the column and scope nothing.
    _head, where, conditions = re.split(r"(\bWHERE\b)", statement, maxsplit=1, flags=re.I) \
        if re.search(r"\bWHERE\b", statement, re.I) else (statement, "", "")
    if touched and not (where and _PREDICATE.search(conditions)):
        return touched
    return []


def sql_literals() -> list[tuple[str, int, str]]:
    """Every string literal in `store/*.py` that is a SQL read, update or delete.

    Adjacent literals are one constant to the parser, so a statement written across several
    lines is checked whole. A clause appended with `+=` is its own literal - which is why a
    tenant-owned FROM must carry its predicate in the SAME literal, not in a later fragment.
    """
    found = []
    for path in sorted(STORE.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and _VERB.match(node.value):
                found.append((path.name, node.lineno, node.value))
    return found


class TestEveryStatementOnATenantTableIsScoped:

    def test_the_store_has_tenant_owned_tables_to_guard(self):
        # `actions` since slice 18, discovered from schema.sql rather than listed here.
        assert {"runs", "verdicts", "evidence", "actions"} <= tenant_owned_tables()

    def test_there_are_statements_to_check(self):
        assert len(sql_literals()) >= 4, "the scan found no SQL - it would pass vacuously"

    def test_no_sql_literal_reads_updates_or_deletes_a_tenant_table_unscoped(self):
        owned = tenant_owned_tables()
        offenders = ["%s:%d touches %s with no tenant predicate"
                     % (name, line, ", ".join(unscoped(sql, owned)))
                     for name, line, sql in sql_literals() if unscoped(sql, owned)]
        assert not offenders, offenders

    def test_no_statement_the_store_actually_executes_is_unscoped(self, tmp_path):
        """The same rule over what SQLite really ran, through every public method, so a
        statement assembled at runtime cannot slip past the literal scan."""
        owned = tenant_owned_tables()
        store = RunStore(tmp_path / "traced.sqlite3")
        executed: list[str] = []
        store._connection.set_trace_callback(executed.append)
        run_id = store.save(a_run("demo"))
        store.save(a_run("demo"))                        # the replace path
        store.load(run_id, tenant_id="demo")
        store.load(run_id, tenant_id="sandbox")
        store.history(tenant_id="demo")
        store.history("checkout_money_owed", tenant_id="demo", limit=5)
        # Slice 18's public methods on the `actions` table, every path through each: a new
        # record, a repeat, a later failure, a later pass, a read, a move, a refused move and
        # another property's attempt. A method added here later must be added to this list.
        from hotelcontrols.actions import DONE, Finding, Findings, TransitionRefused
        at = datetime(2026, 7, 8, 12, tzinfo=timezone.utc)
        later = datetime(2026, 7, 9, 12, tzinfo=timezone.utc)

        def offered(when, failing=True):
            found = Finding(tenant_id="demo", control_id="checkout_money_owed",
                            control_name="C", policy_version=2, policy_digest="sha256:x",
                            record_id="r-demo", severity="high", audience="finance",
                            kind="notify", reason="money owed", run_id="run-%s" % when.day,
                            raised_at=when, as_of=when.date().isoformat(), provider="x",
                            evidence_label="cap")
            return Findings(run_id=found.run_id, tenant_id="demo",
                            control_id="checkout_money_owed", policy_version=2, at=when,
                            as_of=found.as_of, failing=(found,) if failing else (),
                            passing=() if failing else ("r-demo",))

        store.record_findings(offered(at))
        store.record_findings(offered(at))                # the repeat
        store.record_findings(offered(later, failing=False))   # a later pass annotates
        store.record_findings(offered(later))             # failing again
        (record,) = store.actions(tenant_id="demo")
        store.action(record.action_id, tenant_id="demo")
        store.action(record.action_id, tenant_id="sandbox")
        store.transition(record.action_id, DONE, tenant_id="sandbox", at=later, actor="o")
        store.transition(record.action_id, DONE, tenant_id="demo", at=later, actor="o")
        with pytest.raises(TransitionRefused):
            store.transition(record.action_id, DONE, tenant_id="demo", at=later, actor="o")
        store.close()
        reads = [s for s in executed if _VERB.match(s)]
        assert reads, "nothing was traced, so nothing was checked"
        assert not [s for s in reads if unscoped(s, owned)], [
            s for s in reads if unscoped(s, owned)]


class TestTheStructuralRuleItself:
    """Tested on its own, so the guard cannot rot into a test that always passes."""

    OWNED = frozenset({"runs", "verdicts", "evidence", "actions"})

    @pytest.mark.parametrize("statement", [
        "SELECT * FROM runs WHERE run_id = ?",
        "SELECT * FROM verdicts WHERE run_id = ? ORDER BY position",
        "DELETE FROM evidence WHERE run_id = ?",
        "UPDATE actions SET state = 'done' WHERE action_id = ?",
        "SELECT r.run_id FROM runs r LEFT JOIN verdicts v ON v.run_id = r.run_id",
        "SELECT tenant_id FROM runs WHERE run_id = ?",           # named, not a predicate
        "UPDATE actions SET tenant_id = ? WHERE action_id = ?",  # a SET is not a predicate
        "SELECT 1 FROM runs WHERE run_id = ? AND tenant_id != ?",  # every OTHER property
    ])
    def test_an_unscoped_statement_is_caught(self, statement):
        assert unscoped(statement, self.OWNED)

    @pytest.mark.parametrize("statement", [
        "SELECT * FROM runs WHERE run_id = ? AND tenant_id = ?",
        "SELECT v.* FROM verdicts v JOIN runs r ON r.run_id = v.run_id "
        "WHERE v.run_id = ? AND r.tenant_id = ?",
        "DELETE FROM evidence WHERE run_id IN (SELECT run_id FROM runs WHERE run_id = ? "
        "AND tenant_id = ?)",
        "SELECT * FROM runs WHERE tenant_id = 'sandbox'",       # as a trace callback sees it
        "INSERT INTO runs (run_id) VALUES (?)",                  # a write names its own row
        "PRAGMA table_info(runs)",
    ])
    def test_a_scoped_statement_or_a_non_read_passes(self, statement):
        assert unscoped(statement, self.OWNED) == []

    def test_a_table_v3_adds_later_is_covered_without_editing_this_file(self):
        """The ownership list is read from schema.sql, so `actions` (slice 18) and
        `decisions` (slice 22) are guarded the moment their CREATE TABLE lands."""
        assert unscoped("SELECT * FROM decisions WHERE decision_id = ?",
                        frozenset({"decisions"})) == ["decisions"]
