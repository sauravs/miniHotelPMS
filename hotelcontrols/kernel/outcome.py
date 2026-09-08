# -*- coding: utf-8 -*-
"""
OUTCOME - what can happen to one record under one control.

FOUR, NOT THREE
---------------
PASS, FAIL and UNKNOWN are the control's answers. EXCLUDED is the fourth thing that can
happen to a record and deliberately is not one of them: the control did not apply, so it has
no opinion.

Folding EXCLUDED into PASS is the specific mistake this separation prevents. A run over a
hundred reservations where ninety were out of scope would otherwise report "90 passed", and a
compliance number inflated with records nobody checked is worse than no number at all.

`is_answer` exists because of finding F5. Coverage is `PASS + FAIL`: a run in which every
record was EXCLUDED or UNKNOWN concluded nothing about the property, and must not render as a
clean bill of health. v1 reported 28 EXCLUDED / 0 FAIL for an out-of-service-room control on a
property where the mechanism had never once been observed working, and on screen that was
indistinguishable from a clean result.
"""
from __future__ import annotations

from enum import StrEnum


class Outcome(StrEnum):
    """The four things a control can conclude about one record."""

    PASS = "PASS"
    """Everything required is known, and the rule holds."""

    FAIL = "FAIL"
    """Everything required is known, and the rule is violated."""

    UNKNOWN = "UNKNOWN"
    """Not enough evidence. Carries a reason and the fields that are missing.

    Never a softer FAIL. Most hotel controls read "X must not happen unless approved", and no
    PMS records the approval - so this is the honest answer far more often than it is a bug.
    """

    EXCLUDED = "EXCLUDED"
    """The control does not apply to this record. Not an answer - the control has no opinion."""

    @property
    def is_answer(self) -> bool:
        """Whether the control actually concluded something about the record.

        The basis of the coverage verdict (F5). Only PASS and FAIL count.
        """
        return self in (Outcome.PASS, Outcome.FAIL)
