# -*- coding: utf-8 -*-
"""
THE MODEL SEAM - a second front end, and not one gram of extra trust.

Decision D9 (`docs/open-questions.md`, 2026-09-09): **build the seam, exercise it against a
stub. No real model is wired in this slice.** Four reasons are recorded there and the second is
the structural one; the first is the one that matters to this file:

    A stub tests the gate harder than a real model does. The gate's job is to reject a proposal
    naming vocabulary nobody defined, BY NAME. A stub emits exactly the proposals that exercise
    it - an undeclared field, an unknown operator, an aggregate with no group_by, a predicate
    with two right-hand sides. A real model mostly emits plausible IR, which exercises the
    validator least. The thing under test is the gate, not the model.

WHAT THIS CLASS IS
-------------------
One method's worth of adapter. It takes a `Proposer` - anything with `propose(sentence) -> dict`
- and puts whatever comes back through `grammar.finish`, which is the SAME function the
restricted-English front end ends in, which calls the SAME `spec.validate` a hand-written JSON
file goes through. There is no second validation path. A model's proposal is rejected exactly
as a person's is, with the same messages, and the missing vocabulary is named.

WHAT THIS CLASS DELIBERATELY IS NOT
------------------------------------
It does not find a model, hold a key, or make a request. There is no HTTP client in this
package and no import that could become one - asserted over the AST in the unit tests. The
proposer is handed in. If a model is ever wired (D9 records how: `claude-opus-5`, structured
outputs fed from `spec/ir_schema.json`), it belongs in `tools/` as a drafting aid whose output
a person reviews and commits - never a runtime component, because no verdict may depend on a
model call.

CONFIDENCE IS REPORTED, NEVER ACTED ON
---------------------------------------
A proposal's confidence is None here. Nothing in this process established a number, and the
model's opinion of itself is not evidence - the same rule that makes a value nobody could
establish an UNKNOWN rather than a PASS. A high number would not soften the validator and a low
one would not harden it.
"""
from __future__ import annotations

from typing import Any, Protocol

from ..spec import Problem, Registry, TenantConfig
from .grammar import finish
from .problems import LOGIC_KEYS, Compilation


class Proposer(Protocol):
    """Whatever can turn a sentence into a proposed rule. One method, and it returns data."""

    def propose(self, sentence: str) -> dict[str, Any]:
        ...


class ModelCompiler:
    """A proposal front end. Same output type, same gate, no extra trust."""

    __slots__ = ("_registry", "_proposer")

    def __init__(self, registry: Registry, proposer: Proposer) -> None:
        self._registry = registry
        self._proposer = proposer

    def compile(self, sentence: str, deployment: dict[str, Any] | None = None,
                tenant: TenantConfig | None = None) -> Compilation:
        where = "proposal for %r" % sentence
        try:
            proposal = self._proposer.propose(sentence)
        except Exception as exc:                      # noqa: BLE001 - see below
            # A proposer is somebody else's code, and in the wired case it would be somebody
            # else's network. Whatever it does wrong becomes a stated reason, because a
            # traceback out of a compile step reads as an engine defect rather than as a
            # rejected proposal.
            return Compilation(
                problems=(Problem(where, "the proposer failed: %s: %s"
                                  % (type(exc).__name__, exc)),), source="model")

        if not isinstance(proposal, dict):
            return Compilation(
                problems=(Problem(where, "a proposal must be an IR object, and this one is a "
                                         "%s" % type(proposal).__name__),), source="model")

        missing = [key for key in LOGIC_KEYS if key not in proposal]
        if missing:
            # Reported here rather than left to the schema, because "required_evidence is
            # missing" is a statement about the PROPOSAL, and the author needs to know which
            # front end produced the gap before they can do anything about it.
            return Compilation(
                problems=tuple(Problem(where, "the proposal has no %r, so it does not say %s"
                                       % (key, _WHAT[key])) for key in missing),
                logic=dict(proposal), source="model")

        logic = {key: proposal[key] for key in LOGIC_KEYS}
        extra = tuple(Problem(
            where, "the proposal carries %r, which is not the rule's half of the document - a "
                   "proposer proposes the rule, and everything a sentence cannot say without "
                   "naming a PMS arrives as deployment data" % key)
            for key in sorted(set(proposal) - set(LOGIC_KEYS)))
        # And here is the whole seam: one call, into the same function the grammar ends in.
        return finish(logic, deployment, self._registry, sentence, tenant,
                      confidence=None, source="model", extra=extra)


_WHAT = {
    "entity": "what one record is",
    "references": "what property-wide data it joins against",
    "scope": "which records it applies to",
    "exceptions": "which records are exempt",
    "assertion": "what must be true",
    "required_evidence": "what evidence it needs",
}
