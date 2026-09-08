# -*- coding: utf-8 -*-
"""
The subset JSON Schema validator.

`jsonschema` is not in the standard library and criterion 11 says the engine imports nothing
that is not, so this implements only the keywords `spec/ir_schema.json` uses.

The design decision worth testing hardest is the inverted default: AN UNRECOGNISED KEYWORD IS
AN ERROR. A partial implementation that quietly ignores what it does not understand is worse
than no validator, because the schema then looks enforced while permitting anything - the
"green that means nothing" failure this project keeps running into. `test_an_unsupported_
keyword_raises_rather_than_being_ignored` is the guard on that.
"""
import pytest

from hotelcontrols.spec import SchemaFeatureUnsupported
from hotelcontrols.spec import schema as jsonschema


def messages(instance, schema):
    return [str(p) for p in jsonschema.validate(instance, schema)]


class TestTheInvertedDefault:
    def test_an_unsupported_keyword_raises_rather_than_being_ignored(self):
        """If someone adds `oneOf` to the schema tomorrow, this file must demand to be
        extended rather than nodding the constraint through unenforced."""
        with pytest.raises(SchemaFeatureUnsupported) as caught:
            jsonschema.validate({}, {"oneOf": [{"type": "string"}]})
        assert "oneOf" in str(caught.value)

    def test_annotations_are_ignored_deliberately_and_by_name(self):
        """`description` and `title` document; they do not constrain. Listed explicitly in the
        implementation so they are skipped on purpose rather than by accident."""
        assert messages("x", {"type": "string", "description": "a thing", "title": "T"}) == []

    def test_an_unknown_type_name_raises(self):
        with pytest.raises(SchemaFeatureUnsupported):
            jsonschema.validate("x", {"type": "duration"})

    def test_only_local_refs_are_supported(self):
        with pytest.raises(SchemaFeatureUnsupported):
            jsonschema.validate({}, {"$ref": "https://example.com/schema.json"})


class TestTypes:
    @pytest.mark.parametrize("value,declared,ok", [
        ("x", "string", True), (1, "string", False),
        (1, "integer", True), (1.5, "integer", False),
        (1.5, "number", True), ([], "array", True), ({}, "object", True),
        (True, "boolean", True),
    ])
    def test_basic_types(self, value, declared, ok):
        assert (messages(value, {"type": declared}) == []) is ok

    def test_a_boolean_does_not_satisfy_integer(self):
        """bool subclasses int in Python. Without this guard `"version": true` validates."""
        assert messages(True, {"type": "integer"})
        assert messages(True, {"type": "number"})

    def test_a_type_failure_stops_further_checks_on_that_node(self):
        """Reporting "minItems failed" about a string is noise stacked on the real problem."""
        found = messages("not a list", {"type": "array", "minItems": 3})
        assert len(found) == 1
        assert "expected array" in found[0]


class TestConstraints:
    def test_enum(self):
        assert messages("mostly", {"enum": ["all", "any"]})
        assert messages("all", {"enum": ["all", "any"]}) == []

    def test_const(self):
        assert messages(2, {"const": 1})
        assert messages(1, {"const": 1}) == []

    def test_required_names_the_missing_property(self):
        found = messages({"a": 1}, {"type": "object", "required": ["a", "b"]})
        assert len(found) == 1 and "'b'" in found[0]

    def test_additional_properties_false_catches_a_typo(self):
        """The check that stops `assertions` validating while the real `assertion` keeps
        whatever it had."""
        schema = {"type": "object", "properties": {"assertion": {}},
                  "additionalProperties": False}
        found = messages({"assertion": 1, "assertions": 2}, schema)
        assert len(found) == 1 and "assertions" in found[0]

    def test_additional_properties_true_permits_extras(self):
        schema = {"type": "object", "properties": {"a": {}}, "additionalProperties": True}
        assert messages({"a": 1, "b": 2}, schema) == []

    def test_min_items_min_length_min_properties_and_minimum(self):
        assert messages([], {"type": "array", "minItems": 1})
        assert messages("", {"type": "string", "minLength": 1})
        assert messages({}, {"type": "object", "minProperties": 1})
        assert messages(0, {"type": "integer", "minimum": 1})
        assert messages(1, {"type": "integer", "minimum": 1}) == []

    def test_pattern(self):
        assert messages("Not An Id", {"type": "string", "pattern": "^[a-z0-9_]+$"})
        assert messages("checkout_money_owed",
                        {"type": "string", "pattern": "^[a-z0-9_]+$"}) == []


class TestPathsAndNesting:
    def test_a_problem_names_where_it_happened(self):
        """The path is the whole usability of the output: 'expected string' is useless without
        it, and this output is shown to whoever wrote the rule."""
        schema = {"type": "object", "properties": {
            "assertion": {"type": "object", "properties": {
                "predicates": {"type": "array", "items": {
                    "type": "object", "properties": {"field": {"type": "string"}}}}}}}}
        found = messages({"assertion": {"predicates": [{"field": 1}]}}, schema)
        assert found == ["$.assertion.predicates[0].field - expected string, got int"]

    def test_a_local_ref_resolves_through_definitions(self):
        schema = {
            "type": "array", "items": {"$ref": "#/definitions/predicate"},
            "definitions": {"predicate": {"type": "object", "required": ["field"]}}}
        found = messages([{"field": "x"}, {}], schema)
        assert len(found) == 1 and "[1]" in found[0]

    def test_every_problem_is_reported_not_just_the_first(self):
        """A rule author fixing one error at a time, one CI run at a time, is a rule author
        who stops using the validator."""
        schema = {"type": "object", "required": ["a", "b", "c"]}
        assert len(messages({}, schema)) == 3


class TestProblemValue:
    def test_a_problem_reads_as_a_sentence(self):
        from hotelcontrols.spec import Problem
        assert str(Problem("$.assertion", "needs group_by")) == "$.assertion - needs group_by"
        assert "needs group_by" in repr(Problem("$.assertion", "needs group_by"))

    def test_problems_compare_and_hash_so_they_can_be_de_duplicated(self):
        from hotelcontrols.spec import Problem
        assert Problem("a", "b") == Problem("a", "b")
        assert Problem("a", "b") != Problem("a", "c")
        assert Problem("a", "b") != "a - b"
        assert len({Problem("a", "b"), Problem("a", "b")}) == 1
