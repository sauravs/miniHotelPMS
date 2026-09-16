# -*- coding: utf-8 -*-
"""
THE STUB - the only proposer any test wires, and the one that tests the gate hardest.

Decision D9 recorded the argument and D10 keeps it: *a stub tests the gate harder than a real
model does.* The gate's job is to reject a proposal naming vocabulary nobody defined, BY NAME.
A stub emits exactly the replies that exercise it - an undeclared field, a population window a
sentence may not contain, an ambiguous operand, a bare question, a crash. A real model mostly
emits plausible sentences, which exercises the validator least.

It also makes the compose UI demonstrable with nothing installed: no Ollama, no key, no
network. `python3 -m tools.serve --llm stub` is a working chat window that always answers.
"""
from __future__ import annotations

from hotelcontrols.compiler.sentences import Turn

# Prose fragment -> the reply a proposer would give. Matched on the first fragment found in the
# request, so a caller can type naturally and still land on a known answer.
#
# Each entry exists to reach one outcome in the compose flow, and the comment says which.
SCRIPT: tuple[tuple[str, str], ...] = (
    # Compiles, and is a rule this repository does not ship - so a test cannot pass by
    # accidentally matching a filed control.
    ("email", 'every reservation where reservation.status is not "cancelled" '
              'must have reservation.guest.email exists'),
    # Compiles. The shipped checkout rule, reachable from prose a person would actually type.
    # Three spellings of the same idea because "owing" does not contain "owe", and a stub that
    # silently fell through to its fallback would look like a model that failed to understand.
    ("owing", 'every reservation where reservation.status is "checked_out" '
              'must have folio.balance_due at most 0'),
    ("owe", 'every reservation where reservation.status is "checked_out" '
            'must have folio.balance_due at most 0'),
    ("balance", 'every reservation where reservation.status is "checked_out" '
                'must have folio.balance_due at most 0'),
    ("refund", 'every reservation where reservation.status is "checked_out" '
               'must have folio.balance_due at least 0'),
    # REFUSED: names a field no canonical vocabulary declares. The validator must say which.
    ("inspect", "every reservation where reservation.vip is \"true\" "
                "must have room.inspection_status is \"clean\""),
    # REFUSED: a sentence may not choose its own population (criterion 5).
    ("tomorrow", "every reservation arriving tomorrow must have folio.balance_due at most 0"),
    # A QUESTION rather than a guess - section 18. Only the hotel knows its own rate codes.
    ("corporate", "Which rate codes count as corporate at this property? "
                  "I will not guess at hotel policy."),
    ("best available", "How should 'best available room' be decided - highest category, "
                       "highest price, or a ranking the hotel maintains?"),
)

FALLBACK = ("I cannot turn that into a rule yet. Name the fields it is about, or describe what "
            "must be true about one reservation or one room.")


class StubProposer:
    """A fixed, deterministic proposer. No network, no model, no configuration."""

    name = "stub"

    __slots__ = ("_calls",)

    def __init__(self) -> None:
        # Every request made, so a test can assert the conversation carried its history rather
        # than assuming it did.
        self._calls: list[tuple[str, tuple[Turn, ...]]] = []

    @property
    def calls(self) -> tuple[tuple[str, tuple[Turn, ...]], ...]:
        return tuple(self._calls)

    def propose(self, prose: str, history: tuple[Turn, ...] = ()) -> str:
        self._calls.append((prose, tuple(history)))
        lowered = (prose or "").lower()
        for fragment, reply in SCRIPT:
            if fragment in lowered:
                return reply
        return FALLBACK


class ExplodingProposer:
    """A proposer that fails, because somebody else's process is allowed to.

    Exists so the failure path is a stated reason on screen rather than a traceback. It is the
    same guarantee `ModelCompiler` already makes, and it is the difference between "the thing we
    asked could not answer" and "this engine is broken".
    """

    name = "exploding"

    def propose(self, prose: str, history: tuple[Turn, ...] = ()) -> str:
        raise RuntimeError("the model host refused the connection")
