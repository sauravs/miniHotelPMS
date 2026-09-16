# -*- coding: utf-8 -*-
"""
WHAT WE ASK A MODEL, AND THE TWO LOCKS THAT STOP A TEST ASKING IT.

Everything in this package lives OUTSIDE `hotelcontrols/` on purpose. The engine imports only
the standard library (criterion 11) and contains no outbound HTTP client at all; a model client
is exactly the thing that would break both, so it lives here and is INJECTED. The engine-side
seam is `hotelcontrols/compiler/sentences.normalise`, which takes a proposer and never goes
looking for one.

THE PROMPT IS GENERATED, NOT WRITTEN
-------------------------------------
This is the load-bearing decision in this file. The system prompt is assembled at call time
from:

    * the canonical vocabulary            spec/canonical_fields.json  (53 fields)
    * the grammar's own keyword tables    hotelcontrols/compiler/grammar.py
    * the eleven shipped sentences        spec/ir/*.json restricted_language

so it cannot drift from the thing it is describing. A hand-written prompt listing operators
would be a second copy of `OPERATOR_PHRASES`, and the day somebody adds an operator, the model
would be told about a language the compiler no longer speaks. Worse, it would fail SILENTLY:
the model would keep producing sentences that parse, just never using the new operator.

The eleven sentences are included as examples because they are the only sentences in existence
that are known to compile. They are evidence, not decoration - the same argument the fixtures
make.

WHY THIS ASKS FOR SO LITTLE
----------------------------
The model is asked to rewrite one sentence into a template. It is NOT asked to produce JSON,
choose an operator's semantics, decide what evidence a rule needs, or say anything about a PMS.
All of that is the grammar's, and the grammar is deterministic. Decision D10 records why: a
free, locally-run 7B model can do a template rewrite reliably and cannot reliably emit a valid
six-key IR - and "free to run" is a requirement here.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

from hotelcontrols.compiler.grammar import (CLAUSE_WORDS, JOIN_WORDS, OPERATOR_PHRASES,
                                            POPULATION_WORDS, QUANTIFIERS)
from hotelcontrols.compiler.sentences import Turn
from hotelcontrols.spec import available, load
from hotelcontrols.spec.registry import SPEC_DIR

# The one variable that arms a live proposer, named exactly as the transport's is so a grep for
# HOTELCONTROLS_ finds every place this repository decides to talk to something.
ENABLE = "HOTELCONTROLS_COMPOSE"
TRUTHY = ("1", "true", "yes", "on")

# Same list the transport uses, and for the same reason.
TEST_RUNNERS = ("pytest", "_pytest", "unittest", "nose")


class ProposerDisabled(RuntimeError):
    """A live proposer was asked for a sentence and is not armed.

    A `RuntimeError` rather than anything the compiler catches as an evidence gap: being switched
    off is a fact about this process, not a fact about the hotel, and it must not be able to
    turn into a verdict.
    """


# --------------------------------------------------------------------------- the two locks
def is_enabled() -> bool:
    """Lock 1: the environment variable. False unless explicitly truthy."""
    return os.environ.get(ENABLE, "").strip().lower() in TRUTHY


def under_test() -> bool:
    """Lock 2: whether a test runner is loaded in this process.

    Read from `sys.modules` at call time rather than remembered at import, so importing this
    module early cannot defeat it.
    """
    return any(name in sys.modules for name in TEST_RUNNERS)


def assert_armed(what: str) -> None:
    """Refuse unless both locks are open. Called before anything leaves the machine.

    The local backend is held to this too. `localhost` is still a socket, and "no test touches
    the network" is stated without an exception for loopback - a rule with one exception is a
    rule somebody will find a second exception to.
    """
    if not is_enabled():
        raise ProposerDisabled(
            "%s is off. Set %s=1 to arm it. The compose front end is opt-in because it is the "
            "only part of this system that talks to a model at all (decision D10)."
            % (what, ENABLE))
    if under_test():
        raise ProposerDisabled(
            "%s refuses to arm inside a test process (%s is loaded). No test reaches a model "
            "or a network in this repository, and an environment variable alone would be a "
            "lock a test can open in one line - so this is the second one. Tests wire "
            "StubProposer."
            % (what, ", ".join(name for name in TEST_RUNNERS if name in sys.modules)))


# --------------------------------------------------------------------------- the prompt
def vocabulary(spec_dir: pathlib.Path | str = SPEC_DIR) -> list[str]:
    """Every canonical field a rule may name, with its type - read from the registry file."""
    raw = json.loads(
        (pathlib.Path(spec_dir) / "canonical_fields.json").read_text(encoding="utf-8"))
    lines: list[str] = []
    for entity, fields in raw["entities"].items():
        lines.append("  %s:" % entity)
        for spec in fields:
            note = "" if spec.get("resolvable", True) else "   [no provider can supply this]"
            lines.append("    %-42s %s%s" % (spec["field"], spec.get("type", "?"), note))
    return lines


def operators() -> list[str]:
    """The operator phrases, straight out of the grammar's own table."""
    lines = []
    for phrase, positive, negated, operand in OPERATOR_PHRASES:
        said = " ".join(phrase)
        forms = '"%s"' % said
        if negated:
            forms += ' / "is not %s"' % said if said == "one of" else ' / "not %s"' % said
        lines.append("  %-26s -> %-18s operand: %s" % (forms, positive, operand))
    return lines


def examples(spec_dir: pathlib.Path | str = SPEC_DIR, limit: int = 6) -> list[str]:
    """Shipped sentences that are known to compile, newest vocabulary first.

    Read from the spec rather than pasted here, so an example cannot outlive the rule it came
    from. Capped because a 7B model's context is not free and six is enough to fix the shape.
    """
    lines = []
    for control_id in available(spec_dir)[:limit]:
        sentence = load(control_id, spec_dir).get("restricted_language")
        if not sentence:
            continue
        prose = load(control_id, spec_dir).natural_language
        lines.append("  prose:    %s" % prose)
        lines.append("  sentence: %s" % sentence)
        lines.append("")
    return lines


def system_prompt(spec_dir: pathlib.Path | str = SPEC_DIR) -> str:
    """The whole instruction, assembled from the spec and the grammar."""
    return "\n".join([
        "You rewrite a hotel governance rule from plain English into a RESTRICTED ENGLISH",
        "sentence that a deterministic parser accepts. You are a translator, not an author.",
        "",
        "Reply with the sentence ALONE - no preamble, no explanation, no code fence.",
        "",
        "If the rule cannot be written without inventing hotel policy - which rate codes count",
        "as corporate, what 'best available room' means, whether an approval exists - do NOT",
        "guess. Reply with a single short QUESTION instead. A question is always better than a",
        "rule the hotel did not ask for.",
        "",
        "GRAMMAR",
        "  <quantifier> <entity> [joining <entity> by <field> to <field>]",
        "      [where <condition> [and <condition>]...]",
        "      [unless <condition>] must|may have <assertion> [showing <field> and <field>]",
        "",
        "  quantifiers:      %s" % ", ".join(sorted(QUANTIFIERS)),
        "  clause words:     %s" % ", ".join(sorted(CLAUSE_WORDS)),
        "  join words:       %s" % ", ".join(sorted(JOIN_WORDS)),
        "",
        "  A sentence must START with a quantifier. Nothing else counts as a rule.",
        "",
        "OPERATORS - use only these phrasings",
        *operators(),
        "",
        "  A literal string operand is double-quoted: reservation.status is \"checked_out\".",
        "  A number is bare: folio.balance_due at most 0.",
        "",
        "RULES THAT ARE NOT NEGOTIABLE",
        "  1. Write field names out IN FULL from the vocabulary below. Never abbreviate, never",
        "     invent, never use a name that is not listed. An unlisted name is refused by the",
        "     parser and the attempt is wasted.",
        "  2. Never name a property management system, an endpoint, a URL, a wire format or a",
        "     vendor. The rule must not say WHERE evidence comes from.",
        "  3. Never say WHICH RECORDS to fetch - no dates, no windows, no 'arriving tomorrow',",
        "     no 'in the last 24 hours'. That is supplied separately as configuration. These",
        "     words are refused outright: %s." % ", ".join(sorted(POPULATION_WORDS)),
        "  4. State the rule as what must be TRUE, not as what must not happen. 'cannot check",
        "     out owing money' becomes 'must have folio.balance_due at most 0'.",
        "",
        "VOCABULARY - the only field names that exist",
        *vocabulary(spec_dir),
        "",
        "EXAMPLES - real rules from this system, prose and the sentence it becomes",
        *examples(spec_dir),
    ])


def user_prompt(prose: str, history: tuple[Turn, ...] = ()) -> str:
    """The request, carrying why any earlier attempt was rejected.

    Feeding the problems back is what makes a second attempt worth making. Without it a
    proposer that named `room.inspection_status` is asked the same question and gives the same
    answer; with it, it is told that field does not exist and which ones do.
    """
    parts: list[str] = []
    for turn in history:
        parts.append("Earlier in this conversation:")
        parts.append("  they said: %s" % turn.prose)
        if turn.sentence:
            parts.append("  you answered: %s" % turn.sentence)
        if turn.question:
            parts.append("  you asked: %s" % turn.question)
        for problem in turn.problems:
            parts.append("  THE PARSER REFUSED IT: %s" % problem)
        parts.append("")
    if any(turn.problems for turn in history):
        parts.append("Fix the refusal above. Do not repeat the same sentence.")
        parts.append("")
    parts.append("Rewrite this as one restricted English sentence, or ask one question:")
    parts.append(prose.strip())
    return "\n".join(parts)
