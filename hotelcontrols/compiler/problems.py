# -*- coding: utf-8 -*-
"""
WHAT A COMPILATION IS, AND WHAT A SENTENCE IS NOT ALLOWED TO CONTAIN.

Two things live here because they are the same idea from two sides: `Compilation` is what a
front end returns, and `DEPLOYMENT_KEYS` is the list of things it may not have worked out for
itself.

WHY A SENTENCE CANNOT WRITE A WHOLE IR
---------------------------------------
An IR carries a `population.provider_query` - an endpoint and its filters, per provider. That
is one PMS's vocabulary, and criterion 5 says no PMS identifier appears above the provider
layer. A sentence that could name it would be a sentence that breaks the boundary the whole
architecture is built around.

So the compiler splits the document in two. The SENTENCE owns the rule: which entity, which
join, which records are in scope, which are exempt, what must be true, and therefore what
evidence is needed. The DEPLOYMENT owns everything else: which bounded query finds the records
on this PMS, when the control runs, how old its evidence may be, who gets told. That half
arrives as data, from the same place every other piece of `spec/` arrives from.

The split is enforced in both directions. A deployment carrying a `scope` clause is REFUSED,
because then the sentence printed next to a verdict would be a partial account of the rule that
produced it - and an auditable trail whose top line is incomplete is not an auditable trail.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..spec import Problem

# The half of an IR a sentence cannot supply, and must not pretend to.
DEPLOYMENT_KEYS = ("control_id", "version", "name", "source_control", "population",
                   "execution", "freshness_requirement", "unknown_conditions", "action",
                   "caveats")

# The half the sentence owns outright. A deployment naming any of these is refused.
LOGIC_KEYS = ("entity", "references", "scope", "exceptions", "assertion", "required_evidence")

# Written by the compiler from the sentence itself, so they always agree with it.
SENTENCE_KEYS = ("natural_language", "restricted_language")

# Deployment keys the IR schema does not require. Absent is fine; present is used.
OPTIONAL_DEPLOYMENT_KEYS = ("caveats",)

# Why each required deployment key cannot come from a sentence. Shown to whoever wrote the
# sentence, so the answer is "ask for this", not "the compiler said no".
DEPLOYMENT_REASONS = {
    "population": ("a bounded query naming this provider's endpoint and filters - a sentence "
                   "cannot name one without naming a PMS, which criterion 5 forbids, and an "
                   "unbounded control is an unbounded number of calls against somebody "
                   "else's server (R1, R8)"),
    "execution": "when this control runs, and what it falls back to where the events are not published",
    "freshness_requirement": "how old this control's evidence may be before an answer is stale",
    "unknown_conditions": ("the ways this control can legitimately fail to answer - a control "
                           "that cannot say when it is unable to answer is incompletely "
                           "specified"),
    "action": "what happens when it fails, and who hears about it",
    "control_id": "the id this control is filed and re-read under",
    "version": "which revision of this control this is",
    "name": "the human name shown next to a verdict",
    "source_control": "the row in the hotel's own control document this came from",
}


@dataclass(frozen=True, slots=True)
class Compilation:
    """What a front end returns: a rule, or every reason there is not one.

    `ir` is None whenever ANYTHING is wrong. There is no partially-valid IR: a rule that runs
    is a rule that passed the same gate a hand-written one passes, and nothing else.

    `logic` is what the sentence was understood to mean, kept even when the compilation
    failed. An author whose deployment is missing should be able to see that the rule itself
    parsed, rather than being told only that something is absent.

    `confidence` is REPORTED, never acted on. A deterministic parse is 1.0 because the parse is
    exact rather than probable; a model's proposal is None, because nothing here established a
    number and the model's opinion of itself is not evidence. No verdict, and no acceptance
    decision, depends on this field - the validator's answer is the same either way.
    """

    ir: dict[str, Any] | None = None
    problems: tuple[Problem, ...] = ()
    confidence: float | None = None
    ambiguities: tuple[str, ...] = ()
    logic: dict[str, Any] | None = None
    source: str = ""

    @property
    def ok(self) -> bool:
        return self.ir is not None

    def __repr__(self) -> str:
        if self.ok:
            return "Compilation(%s)" % self.ir.get("control_id", "<unnamed>")
        return "Compilation(rejected: %d problem(s), %d ambiguity(ies))" % (
            len(self.problems), len(self.ambiguities))


@dataclass(frozen=True, slots=True)
class _Draft:
    """The clauses a sentence produced, before a deployment is merged onto them."""

    logic: dict[str, Any]
    problems: list[Problem] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)


def deployment_of(raw: dict[str, Any]) -> dict[str, Any]:
    """The non-rule half of an existing IR, for recompiling its sentence against it.

    Used by the round-trip tests and by `tools.validate_spec`: take a shipped control apart,
    compile its restricted-English sentence, and check the rule that comes back is the rule
    that was there. Anything this function does NOT return is something the sentence has to
    account for on its own.
    """
    return {key: raw[key] for key in DEPLOYMENT_KEYS if key in raw}
