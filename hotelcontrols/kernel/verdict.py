# -*- coding: utf-8 -*-
"""
VERDICT - the answer, and what produced it.

    Verdict = (outcome, reason, evidence[(field, value, source)], control_id, record_id)

An unexplained verdict is not auditable, and audit is the product - so a Verdict cannot be
constructed without evidence or without a reason. That is a structural guarantee rather than
a convention somebody has to remember on the day they add the twelfth control.

The requirements doc is explicit about the shape (§20). Not:

    Control failed.

but:

    Payment Guarantee Before Arrival
    Reservation: #84721   Result: FAIL
    Arrival           Sep 2, 3:00 PM
    Hours to arrival  28.3
    Guarantee         None
    Why it failed:    Reservation requires a payment guarantee and none is recorded.

Every field on screen, its value with its unit, and the call it came from.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .errors import NotAuditable
from .outcome import Outcome
from .value import Value


@dataclass(frozen=True, slots=True)
class EvidenceLine:
    """One row of the table that explains a verdict."""

    field: str
    value: Value
    source: str | None = None

    def __post_init__(self) -> None:
        # Provenance defaults to whatever the Value already recorded, so a caller cannot
        # produce a line that claims a different origin from the evidence it contains.
        if self.source is None and self.value.source is not None:
            object.__setattr__(self, "source", self.value.source)

    def __str__(self) -> str:
        return "%s = %s" % (self.field, self.value)


@dataclass(frozen=True, slots=True)
class Verdict:
    """One control's answer about one record, with the evidence that produced it."""

    outcome: Outcome
    reason: str
    evidence: tuple[EvidenceLine, ...]
    control_id: str | None = None
    record_id: str | None = None

    def __init__(self, outcome: Outcome, reason: str, evidence: Iterable[EvidenceLine],
                 control_id: str | None = None, record_id: str | None = None) -> None:
        # A hand-written __init__ so the evidence is COPIED into a tuple at construction.
        # A stored FAIL whose evidence list was appended to afterwards is an accusation with
        # somebody else's receipt attached.
        lines = tuple(evidence)
        if not (reason or "").strip():
            raise NotAuditable("a verdict without a reason cannot be explained to anyone")
        if not lines:
            raise NotAuditable("a verdict without evidence is not auditable")
        object.__setattr__(self, "outcome", Outcome(outcome))
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "evidence", lines)
        object.__setattr__(self, "control_id", control_id)
        object.__setattr__(self, "record_id", record_id)

    @property
    def unknown_fields(self) -> tuple[str, ...]:
        """The evidence lines that are missing - what an UNKNOWN verdict asks a hotel to fix.

        This tuple is the entire commercial value of an UNKNOWN. Without it the answer is
        "we don't know"; with it the answer is "connect this and we will".
        """
        return tuple(line.field for line in self.evidence if not line.value.is_known)

    @property
    def is_answer(self) -> bool:
        """Whether this verdict concluded anything. See Outcome.is_answer and finding F5."""
        return self.outcome.is_answer

    def __str__(self) -> str:
        return "%s %s: %s" % (self.outcome, self.record_id or "", self.reason)

    def __repr__(self) -> str:
        return "Verdict(%s)" % self
