# -*- coding: utf-8 -*-
"""
THE ROUND TRIP - every shipped control's sentence, recompiled, is the control that is shipped.

`plan.md` slice 9 asks for at least 6 of the 11 to round-trip. All eleven do, and the check is
stronger than the one asked for: it is not "the compiled rule reaches the same verdicts", it is
"the compiled rule IS the same rule", clause for clause, and the verdicts follow from that.

WHY EACH CONTROL CARRIES TWO SENTENCES
---------------------------------------
`natural_language` is the prose a person wrote - "A reservation cannot be closed while the guest
still owes money." `restricted_language` is the same rule in the controlled language the
grammar accepts. They are separate on purpose, and the separation is the honest part of this
slice: a grammar taught that "still owes money" means `folio.balance_due at most 0` would be a
phrase book with eleven entries, and a round trip through it would measure the phrase book
rather than the compiler. The prose parses nowhere, that number is recorded in `plan.md`, and
`tests/unit/test_compiler_grammar.py` asserts it stays zero.

WHAT IS COMPARED, AND WHAT IS ALLOWED TO DIFFER
------------------------------------------------
Compared: entity, references, scope, exceptions, the assertion, and the set of evidence fields.
Allowed to differ: `note` - prose annotations a person wrote to explain WHY a predicate is
shaped the way it is, which a compiler has no business inventing. The `source` and `resolvable`
columns of required_evidence are compared by field name only, because the compiler reads those
from the registry rather than from the author.
"""
import copy

import pytest

from hotelcontrols.compiler import compile_sentence, deployment_of
from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers.registry import all_providers
from hotelcontrols.spec import Registry, TenantConfig, available, load
from hotelcontrols.runner import run

# Every control that declares its restricted-English form. Read from the directory rather than
# listed, so a twelfth control is covered from the moment it exists (criterion 6).
COMPILABLE = tuple(c for c in available() if load(c).get("restricted_language"))

# The same three instants and captures the two-provider suite uses, so a disagreement here is
# about the compiler rather than about which body of evidence was asked.
INSTANTS = ("2026-07-08T09:00", "2024-09-01T09:00", "2024-08-14T09:00")
CAPTURES = {
    "2026-07-08T09:00": {"sandbox": "sandbox2026", "demo": "demo2026"},
    "2024-09-01T09:00": {"sandbox": "sandbox2024", "demo": "demo2024"},
    "2024-08-14T09:00": {"sandbox": "sandbox2024", "demo": "demo2024"},
}


@pytest.fixture(scope="module")
def registry():
    return Registry.load()


def without_notes(value):
    """A rule without its prose annotations.

    `note` explains why a predicate is shaped the way it is - "CASE-INSENSITIVE: ARI says
    EXECUTIVE, the room-type master says Executive, and they are the same type (R13)". That is
    knowledge a person had and a compiler does not, and inventing it would be worse than
    omitting it.
    """
    if isinstance(value, dict):
        return {k: without_notes(v) for k, v in value.items() if k != "note"}
    if isinstance(value, list):
        return [without_notes(item) for item in value]
    return value


def recompiled(control_id, registry, tenant=None):
    shipped = copy.deepcopy(load(control_id).raw)
    result = compile_sentence(shipped["restricted_language"], registry,
                              deployment=deployment_of(shipped), tenant=tenant)
    assert result.ir is not None, (
        control_id, [str(p) for p in result.problems], list(result.ambiguities))
    return shipped, result.ir


def test_every_shipped_control_declares_its_restricted_form():
    """The gate this file rests on: a control with no sentence would be silently skipped, and
    the round-trip number would quietly shrink."""
    assert len(COMPILABLE) == len(available()) == 11, COMPILABLE


@pytest.mark.parametrize("control_id", COMPILABLE)
class TestTheSentenceCompilesBackToTheShippedRule:

    def test_the_logic_clauses_are_identical(self, control_id, registry):
        shipped, compiled = recompiled(control_id, registry)
        for clause in ("entity", "references", "scope", "exceptions", "assertion"):
            assert without_notes(compiled[clause]) == without_notes(shipped[clause]), (
                "%s: the compiled %s is not the shipped one" % (control_id, clause))

    def test_it_needs_exactly_the_same_evidence(self, control_id, registry):
        """Check 2 of the gate from the other end. A compiled rule that needed LESS evidence
        would reach the same verdicts with a thinner evidence table, and the table is the
        product (criterion 3)."""
        shipped, compiled = recompiled(control_id, registry)
        assert {e["field"] for e in compiled["required_evidence"]} == \
               {e["field"] for e in shipped["required_evidence"]}

    def test_the_deployment_half_survives_untouched(self, control_id, registry):
        """The compiler must not edit what it was handed. A population query it "improved"
        would be a PMS query written above the provider boundary."""
        shipped, compiled = recompiled(control_id, registry)
        for key in ("population", "execution", "freshness_requirement", "action",
                    "unknown_conditions"):
            assert compiled[key] == shipped[key]


@pytest.mark.parametrize("as_of", INSTANTS)
@pytest.mark.parametrize("control_id", COMPILABLE)
@pytest.mark.parametrize("property_id", ("sandbox", "demo"))
def test_the_compiled_rule_reaches_the_same_verdicts_as_the_hand_written_one(
        control_id, as_of, property_id, registry, tmp_path_factory):
    """Criterion 9, end to end and on both providers.

    The compiled IR is written into a spec directory of its own and RUN - not inspected. The
    runner loads a control by id from a directory, so a compiled rule executes through exactly
    the path a shipped one does, with no import touched. That is also criterion 6 from the
    other end: a control is a file.
    """
    tenant = TenantConfig.load(property_id)
    shipped, compiled = recompiled(control_id, registry, tenant)

    spec_dir = _spec_dir_containing(compiled, tmp_path_factory.mktemp("spec"))
    package = next(p for p in all_providers() if p.name == tenant.provider)
    capture = CAPTURES[as_of][property_id]

    def outcomes(directory):
        adapter, _ = package.build(tenant, capture)
        result = run(control_id, tenant, adapter, FixedClock.at(as_of, tenant.timezone),
                     evidence_label=capture, spec_dir=directory)
        if result.is_blocked:
            return "blocked"
        return sorted((v.record_id, v.outcome.value) for v in result.verdicts)

    from hotelcontrols.spec.registry import SPEC_DIR
    assert outcomes(spec_dir) == outcomes(SPEC_DIR), (
        "%s on %s at %s answers differently when its own sentence is recompiled"
        % (control_id, property_id, as_of))


def _spec_dir_containing(ir, directory):
    """A spec directory holding one compiled control and the vocabulary it is checked against.

    Symlinked rather than copied for everything but the control itself, so this cannot
    accidentally test a stale copy of the registry - the failure mode that a `.pyc` produced in
    v1, one directory along.
    """
    import json
    from hotelcontrols.spec.registry import SPEC_DIR

    (directory / "ir").mkdir(parents=True, exist_ok=True)
    for name in ("canonical_fields.json", "ir_schema.json"):
        target = directory / name
        if not target.exists():
            target.symlink_to(SPEC_DIR / name)
    (directory / "ir" / ("%s.json" % ir["control_id"])).write_text(
        json.dumps(ir, indent=2), encoding="utf-8")
    return directory
