# -*- coding: utf-8 -*-
"""
THE SENTENCE SEAM - prose in, RESTRICTED ENGLISH out, and then the existing grammar.

    normalise(prose, proposer, registry, deployment) -> Normalisation

A third front end, and the first one a person can use without learning a syntax. It sits one
step EARLIER than `model.py`: where `ModelCompiler` asks a proposer for an IR, this asks a
proposer for a SENTENCE, and hands that sentence to `GrammarCompiler` - the same deterministic
parser that has compiled the eleven shipped controls since slice 9.

WHY THE INTERMEDIATE IS A SENTENCE AND NOT JSON
------------------------------------------------
Decision D10. Three reasons, and the third is the one that decided it:

1. A small model is bad at emitting a valid six-key nested IR and good at rewriting a sentence
   into a fixed template. Asking for less makes a FREE, locally-run model adequate rather than
   marginal - and "free to run" is a requirement, not a preference.

2. The intermediate is READABLE. A person sees

       every reservation where reservation.status is "checked_out"
           must have folio.balance_due at least 0

   and can correct it before anything compiles, let alone runs. Raw IR JSON is reviewable in
   principle and unreviewed in practice.

3. NOTHING NEW DECIDES ANYTHING. The rule is still built by the deterministic grammar, still
   validated by the same `spec.validate`, and still carries `confidence=1.0` - because the
   PARSE is exact. What the model did is upstream of the compiler entirely: it proposed a
   sentence, and a sentence is not a rule until the grammar says what it means.

So a wrong field name is not a bad IR that slipped through. It is a sentence the grammar
refuses BY NAME - which is section 17's gate doing exactly the job it was built for.

WHAT THIS MODULE DOES NOT DO
-----------------------------
It does not find a model, hold a key, or make a request. The proposer is handed in, exactly as
`model.py`'s is, and for the same reason: the engine imports only the standard library
(criterion 11), and every model client in this repository lives under `tools/`, outside it.
`tests/unit/test_compiler_grammar.py` asserts over the AST that nothing in this package can
reach a network, and that test passes unchanged.

A PROPOSER MAY ASK A QUESTION INSTEAD OF ANSWERING
---------------------------------------------------
Section 18 is explicit: *"the compiler should not guess... an LLM can interpret language, but it
cannot invent hotel policy."* So a proposer that cannot commit is expected to say so, and the
discriminator is the GRAMMAR'S OWN RULE rather than an invented marker: a rule starts with a
quantifier, so a reply that does not is not a rule. That keeps one definition of "this is a
sentence" in the codebase instead of two.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..spec import Problem, Registry, TenantConfig
from .grammar import QUANTIFIERS, compile_sentence
from .problems import Compilation


@runtime_checkable
class SentenceProposer(Protocol):
    """Whatever can turn prose into restricted English. One method, and it returns text.

    `name` is shown on screen beside the proposal, because a reader deciding whether to trust a
    sentence needs to know what wrote it. It is a label, not a capability.
    """

    name: str

    def propose(self, prose: str, history: tuple[Turn, ...] = ()) -> str:
        ...


@dataclass(frozen=True, slots=True)
class Turn:
    """One exchange, kept so a conversation can carry its own context forward.

    `problems` is the part that earns its place: when a proposal fails to compile, the NEXT
    request carries the reason, so a proposer that named a field nobody declared is told which
    field rather than being asked the same question again.
    """

    prose: str
    sentence: str = ""
    question: str = ""
    problems: tuple[str, ...] = ()

    @property
    def is_question(self) -> bool:
        return bool(self.question)


@dataclass(frozen=True, slots=True)
class Normalisation:
    """What one turn produced: a compiled rule, a question, or the reasons for neither."""

    prose: str
    # Exactly what the proposer said, kept verbatim even when it did not compile. An author
    # cannot correct a sentence they were never shown.
    sentence: str = ""
    question: str = ""
    compilation: Compilation | None = None
    problems: tuple[Problem, ...] = field(default_factory=tuple)
    proposer: str = ""

    @property
    def ok(self) -> bool:
        """Whether this turn produced a rule that is safe to run."""
        return self.compilation is not None and self.compilation.ok

    @property
    def is_question(self) -> bool:
        """Whether the proposer declined to commit and asked for a decision instead."""
        return bool(self.question)

    def as_turn(self) -> Turn:
        """This exchange, in the form the next request carries."""
        reasons = tuple(str(p) for p in self.problems)
        if self.compilation is not None:
            reasons += tuple(str(p) for p in self.compilation.problems)
            reasons += tuple("ambiguous: %s" % a for a in self.compilation.ambiguities)
        return Turn(prose=self.prose, sentence=self.sentence, question=self.question,
                    problems=reasons)


# --------------------------------------------------------------------------- the seam
def normalise(prose: str, proposer: SentenceProposer, registry: Registry,
              deployment: dict[str, Any] | None = None,
              tenant: TenantConfig | None = None,
              ir_schema: dict[str, Any] | None = None,
              history: tuple[Turn, ...] = ()) -> Normalisation:
    """Ask for a sentence, then compile it with the grammar that compiles every other one."""
    name = _name_of(proposer)
    where = "proposal for %r" % _clip(prose)

    if not (prose or "").strip():
        return Normalisation(prose=prose, proposer=name, problems=(
            Problem(where, "there is nothing to compile - describe the rule in a sentence"),))

    try:
        reply = proposer.propose(prose, history)
    except Exception as exc:                          # noqa: BLE001 - deliberate, see below
        # A proposer is somebody else's code, and in the wired case somebody else's process or
        # network. Whatever it does wrong becomes a STATED REASON: a traceback out of a compose
        # step reads as an engine defect, when the honest report is "the thing we asked could
        # not answer". Identical treatment to `ModelCompiler.compile`.
        return Normalisation(prose=prose, proposer=name, problems=(
            Problem(where, "the proposer failed: %s: %s" % (type(exc).__name__, exc)),))

    if not isinstance(reply, str):
        return Normalisation(prose=prose, proposer=name, problems=(
            Problem(where, "a proposal must be a sentence, and this one is a %s"
                    % type(reply).__name__),))

    sentence, question = split_reply(reply)

    if not sentence:
        # Not a failure. A proposer that asks rather than guesses is the behaviour section 18
        # asks for, so it is reported as a question and the conversation continues.
        return Normalisation(prose=prose, question=question or _clip(reply), proposer=name)

    compilation = compile_sentence(sentence, registry, deployment=deployment, tenant=tenant,
                                   ir_schema=ir_schema)
    # `question` survives alongside a sentence: a proposer may commit to a reading AND flag
    # what it assumed, and suppressing that would hide the assumption behind a green result.
    return Normalisation(prose=prose, sentence=sentence, question=question,
                         compilation=compilation, proposer=name)


# --------------------------------------------------------------------------- reply parsing
_FENCE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*$")


def split_reply(reply: str) -> tuple[str, str]:
    """A proposer's raw reply, as (sentence, everything else).

    Models wrap answers in prose and code fences however firmly they are asked not to, and a
    front end that refused anything but a bare sentence would be a front end that fails on
    politeness. So the reply is SCANNED for a rule rather than required to be one.

    The test for "this line begins a rule" is the grammar's own: a rule starts with a
    quantifier. Reusing that rather than inventing a marker keeps one definition of a sentence
    in the codebase - and it means a proposer cannot make something compile by formatting it
    differently.

    A fence is BLANKED rather than dropped, because it is a boundary. Dropping it joined the
    rule to whatever pleasantry followed the closing fence, and the sentence then ended with
    "Hope that helps" - which the grammar rejects, correctly, but about the wrong thing.
    """
    lines = ["" if _FENCE.match(line) else line for line in (reply or "").splitlines()]

    start = None
    for index, line in enumerate(lines):
        first = line.strip().lstrip("-*>").strip().split(" ")[0] if line.strip() else ""
        if first.lower().strip('"') in QUANTIFIERS:
            start = index
            break

    if start is None:
        return "", " ".join(line.strip() for line in lines if line.strip()).strip()

    # A sentence may wrap over several lines - `restricted_language` in the shipped controls
    # runs to three. It ends at the first blank line, so anything the proposer adds afterwards
    # is commentary rather than part of the rule.
    body: list[str] = []
    for line in lines[start:]:
        if not line.strip():
            break
        body.append(line.strip().lstrip("-*>").strip())

    rest = [line.strip() for line in lines[:start] if line.strip()]
    rest += [line.strip() for line in lines[start + len(body):] if line.strip()]
    return " ".join(body).strip(), " ".join(rest).strip()


def _name_of(proposer: Any) -> str:
    """A proposer's label, without trusting it to have one.

    `getattr` is not available here - `tests/unit/test_compiler_grammar.py` forbids it over the
    AST, because a compiler reaching for dynamic attribute access is a compiler one step from
    reaching for `eval`. A declared attribute is read directly and its absence is caught.
    """
    try:
        name = proposer.name
    except AttributeError:
        return type(proposer).__name__
    return str(name) if name else type(proposer).__name__


def _clip(text: str, limit: int = 120) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[:limit - 1] + "…"
