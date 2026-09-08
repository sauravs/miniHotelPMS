# -*- coding: utf-8 -*-
"""
COVERAGE - did this run actually conclude anything?

Review finding F5, and the most valuable thing in this slice.

A run reports four counts. Nothing in v1 distinguished

    "28 rooms checked, all compliant"

from

    "28 rooms, and the control never applied to a single one of them".

Both render as four tiles with a zero under FAIL, and the second one reads as a clean bill of
health. v1's own context document named this danger for controls 1d, 2 and 13 - *"they would
return False and silently pass everything, reporting a clean bill of health while checking
nothing"* - and then the engine shipped without a guard against it.

It is not hypothetical. On the captured evidence today, `ooo_room_protection` excludes all 28
rooms because no room in this property has ever had a closed-date window set, and
`room_capacity_compliance` cannot answer for any stay because the rooms in use report capacity
`0`, meaning unconfigured. Both are the CORRECT answers. Both currently look like success.

So: EVALUATED = PASS + FAIL. A run with `evaluated == 0` concluded nothing, says so, and carries
the reason that dominated - which is what turns "no violations" into "this control could not
look at anything, and here is what to fix".
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..kernel import Outcome


@dataclass(frozen=True, slots=True)
class Coverage:
    """How much of a run's population the control actually reached a conclusion about."""

    evaluated: int
    total: int
    dominant_reason: str | None = None
    # Every reason that stopped this run concluding, with its count, commonest first. A single
    # reason is often the least informative one: 71 of 111 stays are cancelled, which is a
    # correct exclusion and tells a hotel nothing. Showing the distribution lets a reader see
    # both that most records were out of scope AND what happened to the rest.
    reasons: tuple[tuple[str, int], ...] = ()

    @property
    def concluded(self) -> bool:
        """Whether this run says anything at all about the property."""
        return self.evaluated > 0

    @property
    def proportion(self) -> float:
        return (self.evaluated / self.total) if self.total else 0.0

    @property
    def headline(self) -> str:
        """The sentence that goes where the count tiles would otherwise be."""
        if self.total == 0:
            return "This control's population was empty - there was nothing to check."
        if not self.concluded:
            return ("This control reached no conclusion about any of its %d record(s). "
                    "It has not found the property compliant; it has not looked." % self.total)
        if self.evaluated < self.total:
            return ("Concluded about %d of %d record(s); the rest were excluded or could not "
                    "be answered." % (self.evaluated, self.total))
        return "Concluded about every record in the population."


def coverage_of(verdicts) -> Coverage:
    """Measure a run's coverage, and name the reason that dominated when it concluded nothing.

    The dominant reason matters more than the count. "28 rooms excluded" is a number; "no room
    in this property has a closed-date window set" is something a hotel can act on.
    """
    verdicts = list(verdicts)
    evaluated = sum(1 for v in verdicts if v.outcome.is_answer)

    reason = None
    if verdicts and evaluated == 0:
        # UNKNOWN reasons OUTRANK excluded ones, and the precedence is the whole usefulness of
        # this field. When a run concludes nothing there are two different situations:
        #
        #   every record EXCLUDED   the control correctly never applied. Nothing to fix.
        #   some records UNKNOWN    the control applied and could not answer. THAT is the gap,
        #                           and it is what a hotel can act on.
        #
        # Reporting the commonest reason overall buries the second under the first: 71 of 111
        # stays are cancelled, so "this control does not apply here: status is cancelled" wins
        # the popularity contest while the 40 records that actually mattered went unanswered
        # for want of a configured room capacity.
        for outcome in (Outcome.UNKNOWN, Outcome.EXCLUDED):
            counted = Counter(_summarise(v.reason) for v in verdicts if v.outcome is outcome)
            if counted:
                reason = counted.most_common(1)[0][0]
                break

    distribution = Counter(_summarise(v.reason) for v in verdicts if not v.outcome.is_answer)
    return Coverage(evaluated=evaluated, total=len(verdicts), dominant_reason=reason,
                    reasons=tuple(distribution.most_common()))


def _summarise(reason: str) -> str:
    """A reason, trimmed to a length a screen can hold.

    Deliberately NOT split at ", which": that clause is where a comparison says what it could
    not satisfy, and dropping it leaves "guest_count.adults is 2 count" - a sentence about the
    one number that was fine.
    """
    return (reason or "")[:200]
