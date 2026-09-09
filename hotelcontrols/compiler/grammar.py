# -*- coding: utf-8 -*-
"""
THE GRAMMAR COMPILER - restricted English in, Control IR out. Deterministic, offline, no model.

`control_rule_architecture.docx` section 17 asks for stage 1 of six, and is explicit about the
shape it must have:

    Don't go: LLM -> executable JSON directly. That's risky.
    Use: Natural Language -> Control IR -> Validation -> Evidence Requirements
         -> Provider Mapping -> Executable Rule

This module is stage 1. It emits IR - data - and then hands that data to `spec.validate`, which
is the same function that has been policing hand-written rules since slice 1. Nothing here
re-implements a check, and nothing here has a private route around one.

WHAT "RESTRICTED ENGLISH" IS, AND WHY IT IS NOT AN ENGLISH PARSER
-----------------------------------------------------------------
A controlled language: fixed keywords, exactly one reading per sentence, and canonical field
names written out in full.

    every stay joining room by stay.room_number to room.number
        where reservation.status is not "cancelled" and stay.room_number exists
        must have reservation.guest_count.adults at most room.max_guests.adults

Writing the field names out is the load-bearing decision. The alternative - a lexicon mapping
"the guest still owes money" onto `folio.balance_due at most 0` - is a phrase book, and a
phrase book with one entry per shipped control measures itself. It would also put the §17 gate
to sleep: the gate's whole job is to answer "that field does not exist" BY NAME, and it can
only do that if the author named a field.

So the eleven shipped controls carry two sentences. `natural_language` is the prose a person
wrote and this grammar parses none of it. `restricted_language` is the same rule in the
language above, and that is what round-trips. The number is recorded in `docs/plan.md` rather
than engineered away.

AMBIGUITY IS REPORTED, NEVER RESOLVED
--------------------------------------
    reservation.status is cancelled

means either the string "cancelled" or a canonical field named `cancelled`, and the grammar
declines to choose. That is the same commitment as UNKNOWN, one stage earlier: a compiler that
picked a reading would produce a rule that runs, answers, and means something its author did
not write.

THE SENTENCE IS THE RULE, NOT THE DEPLOYMENT
---------------------------------------------
See `problems.py`. Everything a sentence cannot say without naming a PMS arrives as data, and
its absence is reported key by key with the reason.
"""
from __future__ import annotations

import re
from typing import Any

from ..spec import Problem, Registry, TenantConfig, load_schema, validate
from .problems import (DEPLOYMENT_KEYS, DEPLOYMENT_REASONS, LOGIC_KEYS,
                       OPTIONAL_DEPLOYMENT_KEYS, SENTENCE_KEYS, Compilation)

# --------------------------------------------------------------------------- vocabulary
QUANTIFIERS = frozenset({"every", "each", "all", "no"})

# Clause keywords. A word here can never be a field name, which is what makes the sentence
# scannable left to right with no backtracking.
JOIN_WORDS = frozenset({"joining", "collecting"})
CLAUSE_WORDS = JOIN_WORDS | {"where", "unless", "except", "must", "may", "showing"}

# Words that begin a phrase about WHICH RECORDS to look at rather than about the rule. They get
# their own refusal, because "we do not parse that" and "that is not a thing a sentence can
# say" are different answers and only the second one is actionable.
POPULATION_WORDS = frozenset({"arriving", "departing", "staying", "checking", "created",
                              "booked", "cancelled", "in"})

# (phrase, positive operator, negated operator or None, operand kind)
#
# Ordered longest-first at use, so "is not one of" cannot be read as "is not" followed by a
# stray "one". Every operator the IR schema defines appears here: a rule that could be written
# by hand but not said in English would be a rule whose author routes around the compiler.
OPERATOR_PHRASES: tuple[tuple[tuple[str, ...], str, str | None, str], ...] = (
    (("one", "of"), "in", "not_in", "one"),
    (("within",), "within", "not_within", "interval"),
    (("at", "most"), "lte", None, "one"),
    (("at", "least"), "gte", None, "one"),
    (("less", "than"), "lt", None, "one"),
    (("more", "than"), "gt", None, "one"),
    (("greater", "than"), "gt", None, "one"),
    (("exists",), "exists", "not_exists", "none"),
    (("present",), "exists", "not_exists", "none"),
    (("missing",), "not_exists", None, "none"),
    (("resolved",), "reference_exists", "reference_missing", "none"),
    (("unresolved",), "reference_missing", None, "none"),
    (("matching",), "matches_ignore_case", None, "one"),
    (("matches",), "matches_ignore_case", None, "one"),
)

_TOKEN = re.compile(r'"[^"]*"|\S+')
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


class _ParseError(Exception):
    """A sentence this grammar does not accept, with what was expected and where."""


class _Ambiguous(Exception):
    """A sentence with more than one reading. Reported, never resolved."""


# --------------------------------------------------------------------------- the compiler
class GrammarCompiler:
    """Restricted English -> Control IR. Stateless: the same sentence always compiles the same.

    Statelessness is not tidiness. A compiler that remembered anything would make a rule depend
    on what was compiled before it, and a rule that depends on its history cannot be audited.
    """

    __slots__ = ("_registry", "_subject_entities", "_reference_entities")

    def __init__(self, registry: Registry, ir_schema: dict[str, Any] | None = None) -> None:
        self._registry = registry
        schema = ir_schema if ir_schema is not None else load_schema()
        # Read from the schema rather than restated here. The schema is the contract; a second
        # copy of its enums in Python is a second place for the two to disagree.
        self._subject_entities = frozenset(schema["properties"]["entity"]["enum"])
        self._reference_entities = frozenset(
            schema["properties"]["references"]["items"]["properties"]["entity"]["enum"])

    # ------------------------------------------------------------------ public
    def compile(self, sentence: str, deployment: dict[str, Any] | None = None,
                tenant: TenantConfig | None = None) -> Compilation:
        """One sentence, one answer: a validated IR, or every reason there is not one."""
        where = _where(sentence)
        try:
            logic = _Parser(sentence, self._subject_entities,
                            self._reference_entities).parse()
        except _Ambiguous as exc:
            return Compilation(problems=(), ambiguities=(str(exc),), confidence=0.0,
                               source="grammar")
        except _ParseError as exc:
            return Compilation(problems=(Problem(where, str(exc)),), confidence=0.0,
                               source="grammar")

        logic["required_evidence"] = self._evidence(logic)
        # `showing` is a clause of the SENTENCE, not a field of the IR - its whole effect is
        # already in required_evidence. It leaves before the document is assembled.
        logic.pop("showing", None)
        return finish(logic, deployment, self._registry, sentence, tenant,
                      confidence=1.0, source="grammar")

    # ------------------------------------------------------------------ evidence
    def _evidence(self, logic: dict[str, Any]) -> list[dict[str, Any]]:
        """Check 2 of the gate, derived rather than declared twice.

        Whatever the rule reads, it must have declared it needs - so the compiler writes the
        declaration from the sentence and the two cannot drift apart. `source` says WHOSE
        evidence it is, which is what drives the readiness report: "1 of 2 evidence sources
        connected" is the difference between a control that is broken and one the hotel has
        not connected yet (F8).
        """
        # An entity joined `from the hotel` is the hotel's own configuration, not the PMS's.
        # R13 / open question 1.6: a rate code and a price-list code are different key spaces,
        # so nothing inside any PMS we have resolves that join.
        tenant_entities = {r["entity"] for r in logic["references"]
                           if r.get("source") == "tenant"}

        evidence: list[dict[str, Any]] = []
        for name in _fields_in_order(logic):
            entry: dict[str, Any] = {
                "field": name,
                "source": "tenant" if name.split(".")[0] in tenant_entities else "pms"}
            if self._registry.has(name):
                # Read from the vocabulary, never decided here. A field no provider can supply
                # is a property of the registry, not a discovery to be made mid-run.
                entry["resolvable"] = self._registry.field(name).resolvable
            evidence.append(entry)
        return evidence


def compile_sentence(sentence: str, registry: Registry,
                     deployment: dict[str, Any] | None = None,
                     tenant: TenantConfig | None = None,
                     ir_schema: dict[str, Any] | None = None) -> Compilation:
    """`compile(sentence, registry) -> Compilation`, as `architecture.md` L0 declares it."""
    return GrammarCompiler(registry, ir_schema).compile(sentence, deployment, tenant)


# --------------------------------------------------------------------------- the shared gate
def finish(logic: dict[str, Any], deployment: dict[str, Any] | None, registry: Registry,
           sentence: str, tenant: TenantConfig | None = None,
           confidence: float | None = None, source: str = "",
           extra: tuple[Problem, ...] = ()) -> Compilation:
    """Merge the deployment onto the rule and put the result through the existing validator.

    BOTH FRONT ENDS END HERE. That is the point of the seam: a model's proposal is rejected
    exactly as a person's hand-written JSON is, by the same code, with the same messages. A
    second validation path - however small, however well meant - would be a second standard,
    and the weaker one would be the one a model's output travelled down.
    """
    where = _where(sentence)
    deployment = dict(deployment or {})
    problems: list[Problem] = list(extra)

    # The deployment owns the half a sentence cannot say. It does not get to own any of the
    # other half: a smuggled `scope` clause would make the sentence shown beside a verdict a
    # partial account of the rule that produced it.
    for key in sorted(set(deployment) & set(LOGIC_KEYS + SENTENCE_KEYS)):
        problems.append(Problem(
            where, "the deployment carries %r, which is the sentence's half of the rule - a "
                   "rule whose logic is only partly in its sentence cannot be read off the "
                   "screen and checked" % key))
    for key in sorted(set(deployment) - set(DEPLOYMENT_KEYS)):
        problems.append(Problem(where, "the deployment carries %r, which is not part of a "
                                       "control IR" % key))
    for key in DEPLOYMENT_KEYS:
        if key in deployment or key in OPTIONAL_DEPLOYMENT_KEYS:
            continue
        problems.append(Problem(
            where, "this rule still needs %r from whoever deploys it: %s"
                   % (key, DEPLOYMENT_REASONS.get(key, "supplied per property"))))

    raw = {key: value for key, value in deployment.items() if key in DEPLOYMENT_KEYS}
    raw.update(logic)
    # The sentence names itself. A compiled rule's `natural_language` IS the sentence it was
    # compiled from - anything else would print one rule on screen and run another.
    raw["natural_language"] = sentence
    raw["restricted_language"] = sentence

    if not problems:
        # Only worth running once the document is whole: "group_by is missing" about a
        # half-assembled IR is noise addressed to the wrong person.
        problems.extend(validate(raw, registry, tenant=tenant))

    if problems:
        return Compilation(problems=tuple(problems), confidence=confidence, logic=logic,
                           source=source)
    return Compilation(ir=raw, confidence=confidence, logic=logic, source=source)


# --------------------------------------------------------------------------- the parser
class _Parser:
    """One sentence, scanned left to right, with no backtracking and no second reading."""

    def __init__(self, sentence: str, subject_entities: frozenset[str],
                 reference_entities: frozenset[str]) -> None:
        self.tokens = _tokenize(sentence)
        self.at = 0
        self.subject_entities = subject_entities
        self.reference_entities = reference_entities

    # ------------------------------------------------------------------ cursor
    def peek(self, ahead: int = 0) -> str | None:
        index = self.at + ahead
        return self.tokens[index] if index < len(self.tokens) else None

    def word(self, ahead: int = 0) -> str:
        token = self.peek(ahead)
        return token.lower() if token else ""

    def take(self) -> str:
        token = self.peek()
        if token is None:
            raise _ParseError("the sentence ends before the rule does")
        self.at += 1
        return token

    def accept(self, *words: str) -> bool:
        if self.word() in words:
            self.at += 1
            return True
        return False

    def expect(self, word: str, why: str) -> None:
        if not self.accept(word):
            raise _ParseError("expected %r %s, found %s" % (word, why, self._found()))

    def _found(self) -> str:
        token = self.peek()
        return "%r" % token if token is not None else "the end of the sentence"

    def rest(self) -> str:
        return " ".join(self.tokens[self.at:])

    # ------------------------------------------------------------------ sentence
    def parse(self) -> dict[str, Any]:
        quantifier = self._quantifier()
        entity = self._subject()
        references = self._joins()
        scope = self._conditions_after("where") if self.word() == "where" else []
        exceptions = self._exceptions()
        assertion = self._assertion(quantifier)
        showing = self._showing()

        if self.peek() is not None:
            raise _ParseError("the rule ends but the sentence does not: %r" % self.rest())

        return {"entity": entity, "references": references, "scope": scope,
                "exceptions": exceptions, "assertion": assertion, "showing": showing}

    def _quantifier(self) -> str:
        word = self.word()
        if word not in QUANTIFIERS:
            raise _ParseError(
                "a rule starts with %s, and this one starts with %s"
                % (" or ".join("'%s'" % q for q in sorted(QUANTIFIERS)), self._found()))
        self.at += 1
        return word

    def _subject(self) -> str:
        token = self.take()
        if token.lower() not in self.subject_entities:
            raise _ParseError(
                "%r is not something one record can be. A record is one of: %s"
                % (token, ", ".join(sorted(self.subject_entities))))
        return token.lower()

    # ------------------------------------------------------------------ joins
    def _joins(self) -> list[dict[str, Any]]:
        references: list[dict[str, Any]] = []
        while self.word() in JOIN_WORDS:
            kind = "collection" if self.word() == "collecting" else "lookup"
            self.at += 1
            references.append(self._join(kind))
            while self.word() == "and" and self._another_join_follows():
                self.at += 1
                references.append(self._join(kind))
        self._refuse_a_population_phrase()
        return references

    def _another_join_follows(self) -> bool:
        """`and` after a join is another join only when what follows begins one."""
        return self.word(1) == "the" or self.word(1) in self.reference_entities

    def _join(self, kind: str) -> dict[str, Any]:
        if self.accept("the"):
            # `joining the set of room_type.code` - every value of one field across the whole
            # referenced response, for a membership test. Control 1b asks whether a room's type
            # is ONE OF the defined types, which is a set question and not a lookup.
            self.expect("set", "after 'the', for a set reference")
            self.expect("of", "after 'set'")
            field = self._field()
            return {"entity": field.split(".")[0], "kind": "set", "field": field}

        entity = self.take().lower()
        if entity not in self.reference_entities:
            raise _ParseError("%r is not an entity a rule can join to. Joinable: %s"
                              % (entity, ", ".join(sorted(self.reference_entities))))
        # "from the hotel" - the hotel supplies this mapping, because no PMS we have can
        # (R13). Saying so in the rule is what turns a silent UNKNOWN into "connect this".
        source = "tenant" if self.accept("from") else None
        if source:
            self.expect("the", "in 'from the hotel'")
            self.expect("hotel", "in 'from the hotel'")
        self.expect("by", "to name the field on this record that carries the join key")
        local = self._field()
        self.expect("to", "to name the field on the joined record it matches")
        remote = self._field()

        reference = {"entity": entity, "kind": kind, "local_field": local,
                     "remote_field": remote}
        if source:
            reference["source"] = source
        return reference

    def _refuse_a_population_phrase(self) -> None:
        """The one refusal that explains itself rather than just failing.

        "every reservation arriving within 24 hours must ..." is the shape the requirements doc
        uses, and it is the shape that cannot compile. The time window bounds the POPULATION,
        and a population query is one PMS's endpoint and filters (criterion 5). The IR has no
        operator for it either: `within` bounds a record between two canonical fields, not
        between now and now-plus-a-duration. Accepting the sentence would mean inventing one of
        the two, so it is refused by name instead.
        """
        if self.word() in POPULATION_WORDS:
            raise _ParseError(
                "%r describes WHICH RECORDS to look at, and that is the population - a bounded "
                "query naming this provider's endpoint and filters, which a sentence cannot "
                "name without naming a PMS (criterion 5). Supply it in the deployment and say "
                "only the rule here." % self.rest())

    # ------------------------------------------------------------------ clauses
    def _exceptions(self) -> list[dict[str, Any]]:
        """`unless` - a record matching one is EXCLUDED, which is not a pass."""
        if self.accept("except"):
            self.expect("where", "after 'except'")
            return self._conditions()
        if self.word() == "unless":
            return self._conditions_after("unless")
        return []

    def _conditions_after(self, keyword: str) -> list[dict[str, Any]]:
        self.expect(keyword, "to open its clause")
        return self._conditions()

    def _conditions(self) -> list[dict[str, Any]]:
        conditions = [self._condition()]
        while self.word() == "and":
            self.at += 1
            conditions.append(self._condition())
        return conditions

    def _showing(self) -> list[str]:
        """Evidence the verdict table carries that no predicate reads.

        Real controls do this deliberately: `folio.currency` sits next to a balance because a
        reservation and its own folio are in different currencies and no exchange rate exists
        anywhere in the API, so a reader has to see which currency the number is in (R9).
        """
        if not self.accept("showing"):
            return []
        fields = [self._field()]
        while self.accept("and"):
            fields.append(self._field())
        return fields

    # ------------------------------------------------------------------ assertion
    def _assertion(self, quantifier: str) -> dict[str, Any]:
        mode, negated = self._modal(quantifier)
        if self.word() in ("at", "no"):
            return self._aggregate(negated)

        predicates = self._conditions()
        return {"mode": mode, "predicates": predicates}

    def _modal(self, quantifier: str) -> tuple[str, bool]:
        """'must have' / 'must not have' / 'may have', and what each one means.

        "no X may have P" and "every X must not have P" are the same rule said two ways, and
        the engine has one mode for it. A grammar that produced different IR for the two would
        be a grammar whose meaning depended on style.
        """
        if self.accept("must"):
            negated = self.accept("not")
            if not negated and self.word() == "satisfy":
                self.at += 1
                for word in ("at", "least", "one", "of"):
                    self.expect(word, "in 'must satisfy at least one of'")
                return "any", False
            self.expect("have", "after 'must'")
            return ("none" if negated else "all"), negated
        if self.accept("may"):
            if quantifier != "no":
                raise _ParseError(
                    "'may' states a prohibition and needs 'no' in front of the record it is "
                    "about - write 'no %s may have ...' or 'every ... must not have ...'"
                    % (self.tokens[1] if len(self.tokens) > 1 else "record"))
            self.expect("have", "after 'may'")
            return "none", True
        raise _ParseError(
            "expected 'must have', 'must not have' or 'may have' to introduce what the rule "
            "requires, found %s" % self._found())

    def _aggregate(self, negated: bool) -> dict[str, Any]:
        """A question about a GROUP of records, and therefore about a grouping key.

        F2: v1 shipped aggregate assertions with no `group_by` at all, which is why duplicate
        detection could never be evaluated - the rule never said what a duplicate was OF. The
        grammar cannot express one without it: `per <field>` is not optional here.
        """
        if negated:
            raise _ParseError(
                "an aggregate says how many records a group may hold, so it is already a "
                "limit - write 'must have at most N ...' rather than negating it")

        if self.accept("at"):
            self.expect("most", "in 'at most N <field> per <field>'")
            limit = self._integer()
            field = self._field()
            group_by = self._per()
            predicate = {"field": field, "operator": "count_lte", "value": limit}
        else:
            self.expect("no", "in 'no overlapping <field> from <field> to <field> per <field>'")
            self.expect("overlapping", "after 'no'")
            field = self._field()
            self.expect("from", "to open the interval each record occupies")
            start = self._field()
            self.expect("to", "to close the interval")
            end = self._field()
            group_by = self._per()
            predicate = {"field": field, "operator": "no_overlap",
                         "interval": {"start": start, "end": end}}

        if self.word() == "and":
            raise _ParseError(
                "an aggregate assertion asks one question about a group and a record-level "
                "condition asks another about one record; the two have no single answer, so "
                "they cannot share an assertion: %r" % self.rest())
        return {"mode": "aggregate", "group_by": group_by, "predicates": [predicate]}

    def _per(self) -> str:
        self.expect("per", "to name the field the records are grouped by")
        return self._field()

    # ------------------------------------------------------------------ conditions
    def _condition(self) -> dict[str, Any]:
        field = self._field()
        is_seen = self.accept("is")
        negated = self.accept("not")

        matched = self._operator_phrase()
        if matched is None:
            if not is_seen:
                raise _ParseError(
                    "%r is not something this grammar can do to %s. Write 'is', 'is not', "
                    "'one of', 'at most', 'at least', 'less than', 'more than', 'exists', "
                    "'is missing', 'matching', 'within', 'resolved' or 'unresolved'."
                    % (self.peek() or "", field))
            # `<field> is <operand>` with no operator word between them: equality, which is the
            # only reading, so it is not an ambiguity.
            operator, kind = ("not_equals" if negated else "equals"), "one"
        else:
            positive, negative, kind = matched
            if negated and negative is None:
                raise _ParseError(
                    "%r cannot be negated - say the opposite one instead" % positive)
            operator = negative if negated else positive

        predicate: dict[str, Any] = {"field": field, "operator": operator}
        if kind == "one":
            predicate.update(self._operand(field))
        elif kind == "interval":
            start = self._field()
            self.expect("to", "to close the interval this record is measured against")
            predicate["interval"] = {"start": start, "end": self._field()}
        return predicate

    def _operator_phrase(self):
        """Longest match wins, so 'one of' is never read as a stray 'one'."""
        for phrase, positive, negative, kind in sorted(
                OPERATOR_PHRASES, key=lambda item: -len(item[0])):
            if all(self.word(offset) == word for offset, word in enumerate(phrase)):
                self.at += len(phrase)
                return positive, negative, kind
        return None

    def _operand(self, field: str) -> dict[str, Any]:
        """One right-hand side and never two - check 4 of the gate, made structural.

        A condition has one operand slot, so a predicate carrying both a literal and a field to
        compare against cannot be built here at all.
        """
        token = self.peek()
        if token is None:
            raise _ParseError("%s is compared against nothing" % field)
        self.at += 1

        if token.startswith('"') and token.endswith('"') and len(token) >= 2:
            return {"value": token[1:-1]}
        if _NUMBER.match(token):
            return {"value": float(token) if "." in token else int(token)}
        if token.lower() in ("true", "false"):
            return {"value": token.lower() == "true"}
        if token.lower() == "setting":
            # A named list the hotel supplies. v1 carried the placeholder text
            # "<hotel-nominated rate codes>" inside an otherwise executable rule; the IR has a
            # slot for it, and so does the grammar.
            return {"tenant_setting": self.take()}
        if "." in token:
            # A canonical field. Whether it EXISTS is the validator's answer, not the parser's
            # - and it answers by name, which is the whole §17 gate.
            return {"compare_to": token}

        raise _Ambiguous(
            "%r could be the text value \"%s\" or a canonical field name, and the two mean "
            "different rules. Quote it as \"%s\" for the value, or write the field out in "
            "full (entity.field)." % (token, token, token))

    # ------------------------------------------------------------------ atoms
    def _field(self) -> str:
        token = self.take()
        if token.lower() in CLAUSE_WORDS or token.lower() in QUANTIFIERS:
            raise _ParseError("expected a canonical field name, found the keyword %r" % token)
        if "." not in token:
            raise _ParseError(
                "expected a canonical field name like 'reservation.status', found %r. Fields "
                "are written out in full so that one that does not exist can be refused by "
                "name." % token)
        return token

    def _integer(self) -> int:
        token = self.take()
        if not token.isdigit():
            raise _ParseError("expected a whole number, found %r" % token)
        return int(token)


# --------------------------------------------------------------------------- helpers
def _tokenize(sentence: str) -> list[str]:
    tokens = _TOKEN.findall(sentence.strip())
    if tokens and tokens[-1].endswith(".") and not tokens[-1].endswith('"'):
        # A full stop ends the sentence, not a field name. `occupancy.from.` would be a field
        # with a trailing dot, which is why this strips only one and only at the end.
        stripped = tokens[-1][:-1]
        tokens[-1:] = [stripped] if stripped else []
    return tokens


def _where(sentence: str) -> str:
    text = " ".join(sentence.split())
    return "sentence %r" % (text if len(text) <= 70 else text[:67] + "...")


def _fields_in_order(logic: dict[str, Any]) -> list[str]:
    """Every canonical field the rule names, once each, in a stable order.

    Deterministic on purpose: a compiled IR that reordered its own evidence between runs would
    make every diff of a spec file unreadable.
    """
    names: list[str] = []

    def add(name: str | None) -> None:
        if name and name not in names:
            names.append(name)

    for reference in logic["references"]:
        for key in ("local_field", "remote_field", "field"):
            add(reference.get(key))
    for clause in ("scope", "exceptions"):
        for predicate in logic[clause]:
            _add_predicate_fields(predicate, add)
    add(logic["assertion"].get("group_by"))
    for predicate in logic["assertion"]["predicates"]:
        _add_predicate_fields(predicate, add)
    for name in logic.get("showing", ()):
        add(name)
    return names


def _add_predicate_fields(predicate: dict[str, Any], add) -> None:
    add(predicate["field"])
    add(predicate.get("compare_to"))
    interval = predicate.get("interval")
    if interval:
        add(interval.get("start"))
        add(interval.get("end"))
