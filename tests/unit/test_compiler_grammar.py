# -*- coding: utf-8 -*-
"""
STAGE 1 - a sentence becomes a rule, and only a rule.

`control_rule_architecture.docx` section 17 is the whole reason this layer has the shape it
has:

    Don't go: LLM -> executable JSON directly. That's risky.
    Use: Natural Language -> Control IR -> Validation -> Evidence Requirements
         -> Provider Mapping -> Executable Rule

So the compiler emits an IR - data - and hands it to `spec.validate`, which is the code that
was already policing hand-written rules before this slice existed. Nothing here re-implements
a check, relaxes one, or gets a private route around one. A sentence that names a field nobody
declared is rejected by exactly the mechanism that rejects a person who writes the same field
into a JSON file by hand, and the rejection NAMES the field.

WHAT "RESTRICTED ENGLISH" MEANS HERE, AND WHAT IT DELIBERATELY DOES NOT
-----------------------------------------------------------------------
The grammar is a controlled language, not an English parser. It has keywords, one reading per
sentence, and canonical field names written out in full. That last part is the load-bearing
one: a lexicon that mapped the phrase "still owes money" onto `folio.balance_due at most 0`
would be a phrase book with eleven entries in it, and every measurement taken against it would
be a measurement of the phrase book. The eleven shipped controls' `natural_language` sentences
are free prose and this grammar parses none of them - that number is recorded rather than
engineered away, and `TestTheProseSentencesAreNotTheRestrictedLanguage` is where.

Every test below names the IR clause, the success criterion or the risk id it protects.
"""
import ast
import json
import pathlib

import pytest

from hotelcontrols.compiler import (Compilation, GrammarCompiler, compile_sentence,
                                    deployment_of)
from hotelcontrols.spec import Registry, TenantConfig, load

COMPILER = pathlib.Path(__file__).resolve().parents[2] / "hotelcontrols" / "compiler"


@pytest.fixture(scope="module")
def registry():
    return Registry.load()


@pytest.fixture(scope="module")
def deployment():
    """The half of an IR a sentence cannot supply, borrowed from a shipped control.

    A population query names an endpoint and its filters, which is one PMS's vocabulary. A
    sentence that could name it would be a sentence that breaks criterion 5, so the compiler
    takes it as data and says so when it is missing.
    """
    return deployment_of(load("checkout_money_owed").raw)


@pytest.fixture(scope="module")
def tenant():
    return TenantConfig.from_dict({
        "tenant_id": "test", "provider": "minihotel", "timezone": "Asia/Jerusalem",
        "settings": {"nominated_rate_codes": ["RACK"], "rate_plan_permitted_room_types": {}}})


def compiled(sentence, registry, deployment, tenant=None) -> Compilation:
    return compile_sentence(sentence, registry, deployment=deployment, tenant=tenant)


def ir_of(sentence, registry, deployment, tenant=None) -> dict:
    result = compiled(sentence, registry, deployment, tenant)
    assert result.ir is not None, [str(p) for p in result.problems] + list(result.ambiguities)
    return result.ir


# ---------------------------------------------------------------------------------------
class TestTheShapesTheRequirementsDocUses:
    """`plan.md` slice 9, first unit test: the sentence shapes stage 1 has to accept."""

    def test_every_x_must_shape_compiles_to_an_all_assertion(self, registry, deployment):
        ir = ir_of('every reservation where reservation.status is "checked_out" '
                   'must have folio.balance_due at most 0', registry, deployment)
        assert ir["entity"] == "reservation"
        assert ir["scope"] == [{"field": "reservation.status", "operator": "equals",
                                "value": "checked_out"}]
        assert ir["assertion"] == {"mode": "all", "predicates": [
            {"field": "folio.balance_due", "operator": "lte", "value": 0}]}

    def test_no_x_may_shape_compiles_to_a_none_assertion(self, registry, deployment):
        """"no X may ..." and "every X must not ..." are the same rule said two ways, and the
        engine has one mode for it. A grammar that produced different IR for the two would be
        a grammar whose meaning depended on style."""
        one = ir_of('no stay may have stay.room_type matching room.type',
                    registry, deployment)
        other = ir_of('every stay must not have stay.room_type matching room.type',
                      registry, deployment)
        assert one["assertion"]["mode"] == "none"
        assert one["assertion"] == other["assertion"]

    def test_the_unless_shape_becomes_the_exceptions_clause(self, registry, deployment):
        """An exception EXCLUDES a record. It is not a pass, and it is evaluated after scope -
        which is why it compiles to `exceptions` and never to a negated scope predicate."""
        ir = ir_of('every reservation where reservation.status is not "cancelled" '
                   'unless reservation.channel_confirmation_id is missing '
                   'must have reservation.guest.email exists', registry, deployment)
        assert ir["exceptions"] == [{"field": "reservation.channel_confirmation_id",
                                     "operator": "not_exists"}]
        assert ir["scope"] == [{"field": "reservation.status", "operator": "not_equals",
                                "value": "cancelled"}]

    def test_a_population_time_window_is_refused_by_name_rather_than_invented(
            self, registry, deployment):
        """The doc's third shape, "every X arriving within N hours must ...", is the one that
        does NOT compile, and refusing it is the honest answer rather than a gap.

        A time window on arrival bounds the POPULATION, and a population query is one PMS's
        endpoint and filters (criterion 5). The IR has no operator that compares a date to
        "now plus 24 hours" either - `within` bounds a record by two canonical fields. So the
        grammar could only accept this shape by inventing one of the two, and inventing is the
        thing this engine exists not to do. It says which, in a sentence an author can act on.
        """
        result = compiled('every reservation arriving within 24 hours '
                          'must have reservation.guest.email exists', registry, deployment)
        assert result.ir is None
        assert any("population" in str(p) and "arriving within" in str(p)
                   for p in result.problems), [str(p) for p in result.problems]


# ---------------------------------------------------------------------------------------
class TestTheGateSection17AsksFor:
    """Criterion 9's second half: an unsupported sentence is rejected NAMING what is missing."""

    def test_a_sentence_naming_an_undeclared_field_is_rejected_by_name(
            self, registry, deployment):
        result = compiled('every reservation where reservation.vip is true '
                          'must have reservation.guest.email exists', registry, deployment)
        assert result.ir is None
        assert any("reservation.vip" in str(p) and "undeclared" in str(p)
                   for p in result.problems), [str(p) for p in result.problems]

    def test_the_requirements_docs_own_vip_example_is_rejected_naming_both_gaps(
            self, registry, deployment):
        """THE test in this file, and the one `plan.md` slice 1 already ran against a
        hand-written IR. Putting a front end on the validator must not weaken it: the same
        sentence, arriving as English instead of as JSON, is refused for the same two reasons.

        MiniHotel has no VIP flag - the only VIP information in the whole 2026 capture is
        Hebrew prose inside a free-text remarks field (open question 1.5) - and there is no
        housekeeping-status-at-a-time-of-day field either.
        """
        result = compiled(
            'every reservation where reservation.vip is true '
            'must have room.housekeeping_status_at is "clean"', registry, deployment)
        assert result.ir is None
        named = " ".join(str(p) for p in result.problems)
        assert "reservation.vip" in named and "room.housekeeping_status_at" in named, named

    def test_an_undeclared_field_on_the_right_hand_side_is_named_too(
            self, registry, deployment):
        """The easier half to miss. A compare_to is read at evaluation time exactly like the
        left side, so a rule comparing against a field nobody declared answers about nothing
        just as thoroughly."""
        result = compiled('every stay must have stay.room_type matching room.category',
                          registry, deployment)
        assert result.ir is None
        assert any("room.category" in str(p) for p in result.problems), result.problems

    def test_an_unknown_operator_phrase_is_rejected_naming_the_phrase(
            self, registry, deployment):
        result = compiled('every reservation must have folio.balance_due roughly 0',
                          registry, deployment)
        assert result.ir is None
        assert any("roughly" in str(p) for p in result.problems), result.problems

    def test_a_rule_naming_a_tenant_setting_the_hotel_has_not_declared_is_rejected(
            self, registry, deployment, tenant):
        """Check 6 of the existing gate, reached through the compiler. Without it the setting
        resolves empty, scope matches nothing, and the control reports a clean run over zero
        records - finding F5 arriving by a different route."""
        result = compiled('every reservation where stay.rate_code one of setting '
                          'corporate_accounts must have reservation.guest.email exists',
                          registry, deployment, tenant)
        assert result.ir is None
        assert any("corporate_accounts" in str(p) for p in result.problems), result.problems

    def test_a_sentence_the_grammar_cannot_parse_says_where_it_stopped(
            self, registry, deployment):
        result = compiled('reservations should probably be fine', registry, deployment)
        assert result.ir is None
        assert result.problems
        assert any("reservations" in str(p) for p in result.problems), result.problems


# ---------------------------------------------------------------------------------------
class TestAmbiguityIsReportedRatherThanGuessed:
    """`plan.md`: "An ambiguous sentence returns ambiguities rather than a confident guess."

    This is the same commitment as UNKNOWN, one stage earlier. A compiler that picked a reading
    would produce a rule that runs, answers, and means something its author did not write.
    """

    def test_a_bare_word_operand_is_ambiguous_between_a_value_and_a_field(
            self, registry, deployment):
        result = compiled('every reservation where reservation.status is cancelled '
                          'must have reservation.guest.email exists', registry, deployment)
        assert result.ir is None
        assert result.ambiguities
        assert any("cancelled" in a for a in result.ambiguities), result.ambiguities

    def test_the_ambiguity_says_how_to_resolve_it_in_both_directions(
            self, registry, deployment):
        result = compiled('every reservation where reservation.status is cancelled '
                          'must have reservation.guest.email exists', registry, deployment)
        said = " ".join(result.ambiguities)
        assert '"cancelled"' in said, said

    def test_quoting_resolves_it_to_a_literal(self, registry, deployment):
        ir = ir_of('every reservation where reservation.status is "cancelled" '
                   'must have reservation.guest.email exists', registry, deployment)
        assert ir["scope"][0]["value"] == "cancelled"

    def test_a_declared_field_name_resolves_it_to_a_comparison(self, registry, deployment):
        ir = ir_of('every stay must have stay.room_type matching room.type',
                   registry, deployment)
        assert ir["assertion"]["predicates"][0]["compare_to"] == "room.type"
        assert "value" not in ir["assertion"]["predicates"][0]


# ---------------------------------------------------------------------------------------
class TestEveryOperatorTheIrDefines:
    """The grammar covers the IR's operator set, so a rule is never unwritable in English and
    then written by hand in JSON to get around the compiler."""

    CASES = (
        ('reservation.status is "checked_out"', "equals", {"value": "checked_out"}),
        ('reservation.status is not "cancelled"', "not_equals", {"value": "cancelled"}),
        ('room.type one of room_type.code', "in", {"compare_to": "room_type.code"}),
        ('room.type not one of room_type.code', "not_in", {"compare_to": "room_type.code"}),
        ('stay.room_number exists', "exists", {}),
        ('stay.room_number is missing', "not_exists", {}),
        ('reservation.guest_count.adults at most 2', "lte", {"value": 2}),
        ('reservation.guest_count.adults at least 2', "gte", {"value": 2}),
        ('reservation.guest_count.adults less than 2', "lt", {"value": 2}),
        ('reservation.guest_count.adults more than 2', "gt", {"value": 2}),
        ('stay.room_type matching room.type', "matches_ignore_case",
         {"compare_to": "room.type"}),
        ('room.number resolved', "reference_exists", {}),
        ('room.number unresolved', "reference_missing", {}),
    )

    @pytest.mark.parametrize("phrase,operator,extra", CASES)
    def test_the_phrase_compiles_to_the_operator(self, phrase, operator, extra,
                                                 registry, deployment):
        ir = ir_of('every stay must have %s' % phrase, registry, deployment)
        predicate = ir["assertion"]["predicates"][0]
        assert predicate["operator"] == operator
        for key, value in extra.items():
            assert predicate[key] == value

    def test_an_interval_operator_carries_the_two_fields_that_bound_it(
            self, registry, deployment):
        ir = ir_of('every stay must not have reservation.arrival_date within '
                   'room.closed_from to room.closed_to', registry, deployment)
        predicate = ir["assertion"]["predicates"][0]
        assert predicate["operator"] == "within"
        assert predicate["interval"] == {"start": "room.closed_from", "end": "room.closed_to"}

    def test_a_tenant_setting_is_a_third_kind_of_right_hand_side(
            self, registry, deployment, tenant):
        """Not a literal. v1 carried the placeholder text "<hotel-nominated rate codes>" inside
        an otherwise executable rule; the IR has a slot for it and so does the grammar."""
        ir = ir_of('every reservation where stay.rate_code one of setting nominated_rate_codes '
                   'must have reservation.guest.email exists', registry, deployment, tenant)
        assert ir["scope"] == [{"field": "stay.rate_code", "operator": "in",
                                "tenant_setting": "nominated_rate_codes"}]

    def test_a_predicate_never_gets_two_right_hand_sides(self, registry, deployment):
        """Check 4 of the gate, structurally impossible to reach from the grammar: a condition
        has one operand slot. Asserted so a future grammar change cannot quietly open it."""
        ir = ir_of('every stay must have stay.room_type matching room.type',
                   registry, deployment)
        predicate = ir["assertion"]["predicates"][0]
        assert sum(k in predicate for k in ("value", "compare_to", "tenant_setting")) == 1


# ---------------------------------------------------------------------------------------
class TestAggregateAssertions:
    """F2: v1 declared aggregate assertions with no grouping key, so duplicate detection could
    never be evaluated - the rule never said what a duplicate was OF."""

    def test_at_most_n_per_field_compiles_to_count_lte_with_its_group_by(
            self, registry, deployment):
        ir = ir_of('every reservation must have at most 1 reservation.id '
                   'per reservation.channel_confirmation_id', registry, deployment)
        assert ir["assertion"] == {
            "mode": "aggregate", "group_by": "reservation.channel_confirmation_id",
            "predicates": [{"field": "reservation.id", "operator": "count_lte", "value": 1}]}

    def test_no_overlapping_compiles_to_no_overlap_with_its_interval_and_group_by(
            self, registry, deployment):
        ir = ir_of('every occupancy must have no overlapping occupancy.reservation_id '
                   'from occupancy.from to occupancy.to per occupancy.room_number',
                   registry, deployment)
        assert ir["assertion"] == {
            "mode": "aggregate", "group_by": "occupancy.room_number",
            "predicates": [{"field": "occupancy.reservation_id", "operator": "no_overlap",
                            "interval": {"start": "occupancy.from", "end": "occupancy.to"}}]}

    def test_an_aggregate_may_not_be_mixed_with_a_record_level_condition(
            self, registry, deployment):
        """The existing gate refuses it (check 5) and so the compiler must not build it: a
        group question and a record question in one assertion have no single answer."""
        result = compiled('every reservation must have at most 1 reservation.id '
                          'per reservation.channel_confirmation_id '
                          'and reservation.guest.email exists', registry, deployment)
        assert result.ir is None
        assert result.problems


# ---------------------------------------------------------------------------------------
class TestReferencesAreDeclarative:
    """F1: a join to property-wide data, fetched once per run. v1 had no way to say this, so
    three controls returned 111 UNKNOWN out of 111 records."""

    def test_a_lookup_join_names_both_sides(self, registry, deployment):
        ir = ir_of('every stay joining room by stay.room_number to room.number '
                   'must have room.number resolved', registry, deployment)
        assert ir["references"] == [{"entity": "room", "kind": "lookup",
                                     "local_field": "stay.room_number",
                                     "remote_field": "room.number"}]

    def test_a_collection_join_is_the_other_direction(self, registry, deployment):
        """Control 2 starts from the room side and wants every segment booked into it, which
        is the reverse of a lookup and a different word in the grammar for that reason."""
        ir = ir_of('every room collecting occupancy by room.number to occupancy.room_number '
                   'must not have occupancy.reservation_id within room.closed_from '
                   'to room.closed_to', registry, deployment)
        assert ir["references"] == [{"entity": "occupancy", "kind": "collection",
                                     "local_field": "room.number",
                                     "remote_field": "occupancy.room_number"}]

    def test_a_set_reference_collects_one_fields_values_across_the_response(
            self, registry, deployment):
        ir = ir_of('every stay joining the set of room_type.code '
                   'must have room.type one of room_type.code', registry, deployment)
        assert ir["references"] == [{"entity": "room_type", "kind": "set",
                                     "field": "room_type.code"}]

    def test_a_hotel_supplied_reference_says_the_evidence_is_not_the_pmss(
            self, registry, deployment):
        """R13 and open question 1.6: a reservation's rate code and the price-list code are
        different key spaces, so nothing inside the PMS resolves this join. The hotel supplies
        it or the control answers UNKNOWN - and the IR has to say which."""
        ir = ir_of('every stay joining rate_plan from the hotel by stay.rate_code '
                   'to rate_plan.code must have stay.room_type one of '
                   'rate_plan.permitted_room_types', registry, deployment)
        assert ir["references"][0]["source"] == "tenant"

    def test_two_joins_in_one_sentence(self, registry, deployment):
        ir = ir_of('every stay joining room by stay.room_number to room.number and the set of '
                   'room_type.code must have room.number resolved', registry, deployment)
        assert [r["entity"] for r in ir["references"]] == ["room", "room_type"]


# ---------------------------------------------------------------------------------------
class TestRequiredEvidenceIsDerivedNotGuessed:
    """Check 2 of the gate: whatever a rule reads, it declared it needs. The compiler derives
    the declaration from the sentence, so the two cannot drift apart."""

    def test_every_field_the_sentence_mentions_is_declared(self, registry, deployment):
        ir = ir_of('every stay joining room by stay.room_number to room.number '
                   'where reservation.status is not "cancelled" '
                   'must have reservation.guest_count.adults at most room.max_guests.adults',
                   registry, deployment)
        assert {e["field"] for e in ir["required_evidence"]} == {
            "stay.room_number", "room.number", "reservation.status",
            "reservation.guest_count.adults", "room.max_guests.adults"}

    def test_showing_adds_evidence_the_verdict_table_carries_but_no_predicate_reads(
            self, registry, deployment):
        """Real controls carry context on the evidence table that no predicate tests -
        `folio.currency` next to a balance, because a reservation and its own folio are in
        different currencies and a reader has to see which one the number is in (R9)."""
        ir = ir_of('every reservation must have folio.balance_due at most 0 '
                   'showing folio.currency and reservation.currency', registry, deployment)
        assert {e["field"] for e in ir["required_evidence"]} == {
            "folio.balance_due", "folio.currency", "reservation.currency"}

    def test_evidence_from_a_hotel_supplied_reference_is_marked_as_the_hotels(
            self, registry, deployment):
        """Drives the readiness report: "1 of 2 evidence sources connected" is the difference
        between a control that is broken and one that is not connected yet (F8)."""
        ir = ir_of('every stay joining rate_plan from the hotel by stay.rate_code '
                   'to rate_plan.code must have stay.room_type one of '
                   'rate_plan.permitted_room_types', registry, deployment)
        sources = {e["field"]: e["source"] for e in ir["required_evidence"]}
        assert sources["rate_plan.permitted_room_types"] == "tenant"
        assert sources["stay.room_type"] == "pms"

    def test_an_unresolvable_field_is_declared_unresolvable(self, registry, deployment):
        """Read from the registry, not decided here. `rate_plan.permitted_room_types` is
        unresolvable inside any PMS we have (R13), and a compiled rule must say so."""
        ir = ir_of('every stay joining rate_plan from the hotel by stay.rate_code '
                   'to rate_plan.code must have stay.room_type one of '
                   'rate_plan.permitted_room_types', registry, deployment)
        entry = next(e for e in ir["required_evidence"]
                     if e["field"] == "rate_plan.permitted_room_types")
        assert entry["resolvable"] is False


# ---------------------------------------------------------------------------------------
class TestTheSentenceIsTheRuleAndNotTheDeployment:
    """A sentence cannot name a population query without naming a PMS (criterion 5), so it
    does not try. The compiler says what it needs and from whom."""

    def test_a_missing_deployment_is_reported_key_by_key(self, registry):
        result = compile_sentence(
            'every reservation must have folio.balance_due at most 0', registry)
        assert result.ir is None
        named = " ".join(str(p) for p in result.problems)
        for key in ("population", "execution", "action", "control_id"):
            assert key in named, named

    def test_the_reason_names_the_boundary_rather_than_just_the_missing_key(self, registry):
        result = compile_sentence(
            'every reservation must have folio.balance_due at most 0', registry)
        assert any("population" in str(p) and "provider" in str(p)
                   for p in result.problems), [str(p) for p in result.problems]

    def test_the_logic_is_still_shown_so_the_author_can_see_what_was_understood(
            self, registry):
        result = compile_sentence(
            'every reservation must have folio.balance_due at most 0', registry)
        assert result.logic is not None
        assert result.logic["assertion"]["predicates"][0]["field"] == "folio.balance_due"

    def test_the_deployment_may_not_overwrite_the_rule(self, registry, deployment):
        """The half a sentence supplies is the half a sentence owns. A deployment that could
        also carry a scope clause would make the sentence on screen a partial account of the
        rule that ran."""
        smuggled = dict(deployment)
        smuggled["assertion"] = {"mode": "all", "predicates": [
            {"field": "reservation.guest.email", "operator": "exists"}]}
        result = compile_sentence('every reservation must have folio.balance_due at most 0',
                                  registry, deployment=smuggled)
        assert result.ir is None
        assert any("assertion" in str(p) for p in result.problems), result.problems

    def test_the_compiled_rule_carries_the_sentence_it_came_from(self, registry, deployment):
        sentence = 'every reservation must have folio.balance_due at most 0'
        ir = ir_of(sentence, registry, deployment)
        assert ir["natural_language"] == sentence
        assert ir["restricted_language"] == sentence


# ---------------------------------------------------------------------------------------
class TestTheCompilerEmitsIrOnly:
    """The slice gate, and section 17's whole point. Never executable anything."""

    def test_the_output_is_json_data_and_nothing_else(self, registry, deployment):
        ir = ir_of('every reservation where reservation.status is "checked_out" '
                   'must have folio.balance_due at most 0', registry, deployment)
        assert json.loads(json.dumps(ir)) == ir

    def test_the_compiler_never_calls_eval_exec_compile_or_import(self):
        """Asserted over the AST rather than by reading the code, so a future edit is caught.

        A compiler that reached for `eval` to evaluate a comparison would have turned a
        sentence into executable code, which is the one thing section 17 says not to build.
        """
        forbidden = {"eval", "exec", "compile", "__import__", "globals", "locals", "getattr",
                     "setattr"}
        offenders = []
        for path in sorted(COMPILER.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                        and node.func.id in forbidden:
                    offenders.append("%s calls %s" % (path.name, node.func.id))
        assert not offenders, offenders

    def test_no_path_in_the_compiler_can_reach_a_model_or_the_network(self):
        """`plan.md` slice 9: "No test path can reach a real model or the network."

        Decision D9 is that the model adapter is a SEAM in this slice. The seam takes a
        proposer object; it does not go and find one. There is nothing in this package to
        make a request with.
        """
        forbidden = {"urllib", "http", "socket", "ssl", "asyncio", "subprocess", "anthropic",
                     "openai"}
        offenders = []
        for path in sorted(COMPILER.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module.split(".")[0]]
                else:
                    continue
                offenders.extend("%s imports %s" % (path.name, n)
                                 for n in names if n in forbidden)
        assert not offenders, offenders


# ---------------------------------------------------------------------------------------
class TestTheProseSentencesAreNotTheRestrictedLanguage:
    """The measurement, recorded rather than engineered away.

    Each shipped control carries two sentences: the prose a person wrote
    (`natural_language`) and the restricted-English form the grammar accepts
    (`restricted_language`). The grammar parses none of the prose, and that is the honest
    number. Teaching it that "still owes money" means `folio.balance_due at most 0` would be
    writing an eleven-entry phrase book and then measuring the phrase book.
    """

    def test_no_shipped_prose_sentence_parses(self, registry, deployment):
        from hotelcontrols.spec import available
        parsed = [c for c in available()
                  if compile_sentence(load(c).natural_language, registry,
                                      deployment=deployment).ir is not None]
        assert parsed == [], (
            "a prose sentence now parses, which means the grammar has grown a phrase book "
            "or a sentence was tuned to fit it: %s" % parsed)

    def test_and_each_one_is_refused_with_a_reason_rather_than_a_crash(
            self, registry, deployment):
        from hotelcontrols.spec import available
        for control_id in available():
            result = compile_sentence(load(control_id).natural_language, registry,
                                      deployment=deployment)
            assert result.problems or result.ambiguities, control_id


# ---------------------------------------------------------------------------------------
def test_the_grammar_compiler_is_a_pure_function_of_its_inputs(registry, deployment):
    """Same sentence, same IR - twice, and from two instances. A compiler with state would
    make a rule depend on what was compiled before it."""
    sentence = ('every stay joining room by stay.room_number to room.number '
                'where stay.room_number exists must have room.number resolved')
    first = GrammarCompiler(registry).compile(sentence, deployment=deployment)
    second = GrammarCompiler(registry).compile(sentence, deployment=deployment)
    assert first.ir == second.ir


# ---------------------------------------------------------------------------------------
class TestEveryRefusalSaysWhatToDoInstead:
    """A rejected sentence is addressed to whoever wrote it.

    That is the difference between this compiler and a parser: an author who is told "syntax
    error at token 7" writes the rule as a JSON file instead, and the gate is then only as good
    as their patience. Every refusal below names the thing it refused and what to write.
    """

    REFUSALS = (
        ("a sentence that stops mid-rule",
         'every', "ends before the rule does"),
        ("a join with no key",
         'every stay joining room stay.room_number to room.number '
         'must have room.number resolved', "'by'"),
        ("words after the rule has ended",
         'every reservation must have reservation.guest.email exists as soon as possible',
         "the rule ends but the sentence does not"),
        ("a join to something that is not an entity",
         'every stay joining widget by stay.room_number to room.number '
         'must have room.number resolved', "not an entity a rule can join to"),
        ("'may' without the 'no' that makes it a prohibition",
         'every stay may have stay.room_number exists', "'no"),
        ("a negated aggregate",
         'every reservation must not have at most 1 reservation.id '
         'per reservation.channel_confirmation_id', "already a limit"),
        ("negating an operator that has no opposite",
         'every stay must have reservation.guest_count.adults is not at most 2',
         "cannot be negated"),
        ("a comparison with nothing on the right",
         'every reservation must have folio.balance_due at most', "compared against nothing"),
        ("a keyword where a field belongs",
         'every reservation must have showing exists', "found the keyword"),
        ("a field that is not entity-qualified",
         'every reservation must have balance exists', "written out in full"),
        ("a count that is not a number",
         'every reservation must have at most many reservation.id per reservation.channel',
         "expected a whole number"),
    )

    @pytest.mark.parametrize("label,sentence,said", REFUSALS, ids=[r[0] for r in REFUSALS])
    def test_the_refusal_names_what_is_wrong(self, label, sentence, said, registry,
                                             deployment):
        result = compiled(sentence, registry, deployment)
        assert result.ir is None, label
        assert any(said in str(p) for p in result.problems), \
            "%s: %s" % (label, [str(p) for p in result.problems])


class TestTheRemainingClauseForms:
    """Forms the eleven shipped controls do not happen to use. They are tested because an
    untested branch of a grammar is a branch that will be discovered by whoever first writes a
    sentence nobody anticipated."""

    def test_except_where_is_the_long_form_of_unless(self, registry, deployment):
        short = ir_of('every reservation where reservation.status is not "cancelled" '
                      'unless reservation.channel_confirmation_id is missing '
                      'must have reservation.guest.email exists', registry, deployment)
        long = ir_of('every reservation where reservation.status is not "cancelled" '
                     'except where reservation.channel_confirmation_id is missing '
                     'must have reservation.guest.email exists', registry, deployment)
        assert short["exceptions"] == long["exceptions"]

    def test_must_satisfy_at_least_one_of_is_the_any_mode(self, registry, deployment):
        """Kleene's third shape: any True passes, else any unknown is UNKNOWN, else FAIL. The
        IR has the mode, so the grammar has a phrase for it - a rule that could be written by
        hand but not said in English would be a rule whose author routes around the gate."""
        ir = ir_of('every reservation must satisfy at least one of '
                   'reservation.guest.email exists and reservation.guest.phone exists',
                   registry, deployment)
        assert ir["assertion"]["mode"] == "any"
        assert len(ir["assertion"]["predicates"]) == 2

    def test_a_boolean_literal_is_a_boolean_and_not_the_word(self, registry, deployment):
        ir = ir_of('every reservation must have reservation.is_group is false',
                   registry, deployment)
        assert ir["assertion"]["predicates"][0]["value"] is False

    def test_a_decimal_literal_keeps_its_fraction(self, registry, deployment):
        ir = ir_of('every reservation must have folio.balance_due at most 0.5',
                   registry, deployment)
        assert ir["assertion"]["predicates"][0]["value"] == 0.5

    def test_a_trailing_full_stop_ends_the_sentence_and_not_a_field_name(
            self, registry, deployment):
        ir = ir_of('every reservation must have reservation.guest.email exists.',
                   registry, deployment)
        assert ir["assertion"]["predicates"][0]["field"] == "reservation.guest.email"


def test_a_compilation_says_whether_it_produced_a_rule(registry, deployment):
    """`Compilation.ok` and its repr are what a caller reads first - a tool printing
    "Compilation(rejected: 2 problem(s))" is telling somebody something; printing an object
    address is not."""
    good = compiled('every reservation must have reservation.guest.email exists',
                    registry, deployment)
    bad = compiled('every reservation must have reservation.vip exists', registry, deployment)
    assert good.ok and not bad.ok
    assert "checkout_money_owed" in repr(good)
    assert "rejected" in repr(bad) and "1 problem" in repr(bad)
