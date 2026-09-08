# -*- coding: utf-8 -*-
"""Spec-layer failures. Every one of them means: fix the spec, not the engine."""


class SpecError(ValueError):
    """The specification says something the engine cannot act on.

    Raised rather than returned as UNKNOWN, and the distinction matters. An UNKNOWN is a
    statement about a HOTEL - we looked and the evidence was not there. A SpecError is a
    statement about US - the rule references vocabulary nobody defined, or a setting nobody
    declared. Turning one into the other would let a broken control ship looking like a
    control whose evidence is merely missing, and the hotel would go looking for data that
    was never the problem.
    """


class Problem:
    """One validation finding, addressed to whoever wrote the spec.

    A dataclass would do, but validation output is read by people - including, eventually, an
    author whose compiled sentence was rejected - so the string form is the point.
    """

    __slots__ = ("where", "message")

    def __init__(self, where: str, message: str) -> None:
        self.where = where
        self.message = message

    def __str__(self) -> str:
        return "%s - %s" % (self.where, self.message)

    def __repr__(self) -> str:
        return "Problem(%s)" % self

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Problem):
            return NotImplemented
        return (self.where, self.message) == (other.where, other.message)

    def __hash__(self) -> int:
        return hash((self.where, self.message))
