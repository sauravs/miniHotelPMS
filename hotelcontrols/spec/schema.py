# -*- coding: utf-8 -*-
"""
A deliberately small JSON Schema validator.

`jsonschema` is not in the standard library, and success criterion 11 says the engine imports
nothing that is not. So this implements the SUBSET that `spec/ir_schema.json` actually uses -
and nothing more, on purpose. A partial implementation that silently ignores a keyword it does
not understand would be worse than no validator at all: the schema would look enforced while
quietly permitting anything, which is precisely the class of failure this project exists to
avoid.

So the rule is inverted: AN UNRECOGNISED KEYWORD IS AN ERROR. If someone adds `oneOf` to the
schema tomorrow, this file raises and demands to be extended, rather than nodding it through.

Supported: type, enum, const, required, properties, additionalProperties, items, $ref,
definitions, minItems, minLength, minProperties, minimum, pattern, default, description, title,
$schema.
"""
from __future__ import annotations

import re
from typing import Any

from .errors import Problem

# Keywords that carry documentation or defaults rather than constraints. Listed explicitly so
# they are ignored ON PURPOSE rather than by accident.
_ANNOTATIONS = frozenset({"description", "title", "$schema", "default", "definitions"})

_TYPES: dict[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}


class SchemaFeatureUnsupported(NotImplementedError):
    """The schema uses a keyword this validator does not implement.

    Raised rather than ignored. See the module docstring: a validator that skips what it does
    not understand reports a green that means nothing.
    """


def validate(instance: Any, schema: dict[str, Any], *, root: dict[str, Any] | None = None,
             path: str = "") -> list[Problem]:
    """Every way `instance` fails `schema`, as a list of Problems. Empty means valid."""
    root = root if root is not None else schema
    problems: list[Problem] = []
    _check(instance, schema, root, path or "$", problems)
    return problems


def _where(path: str) -> str:
    return path or "$"


def _check(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str,
           out: list[Problem]) -> None:
    if "$ref" in schema:
        _check(value, _resolve(schema["$ref"], root), root, path, out)
        return

    for keyword in schema:
        if keyword not in _ANNOTATIONS and keyword not in _HANDLERS and keyword != "$ref":
            raise SchemaFeatureUnsupported(
                "spec/ir_schema.json uses the keyword %r at %s, which this validator does not "
                "implement. Extend hotelcontrols/spec/schema.py rather than letting the "
                "keyword be silently ignored" % (keyword, _where(path)))

    # `type` first: every other keyword's meaning depends on it, and reporting "minItems failed"
    # about a string is noise on top of the real problem.
    declared = schema.get("type")
    if declared is not None and not _type_ok(value, declared):
        out.append(Problem(_where(path),
                           "expected %s, got %s" % (declared, type(value).__name__)))
        return

    for keyword, handler in _HANDLERS.items():
        if keyword in schema and keyword != "type":
            handler(value, schema, root, path, out)


def _type_ok(value: Any, declared: str) -> bool:
    expected = _TYPES.get(declared)
    if expected is None:
        raise SchemaFeatureUnsupported("unknown JSON Schema type %r" % (declared,))
    # bool is a subclass of int in Python; a flag is not a number, and letting `true` satisfy
    # `integer` would allow `"version": true`.
    if declared in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, expected)


def _resolve(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise SchemaFeatureUnsupported("only local $refs are supported, got %r" % (ref,))
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


# --------------------------------------------------------------------------- keywords
def _enum(value, schema, root, path, out):
    if value not in schema["enum"]:
        out.append(Problem(_where(path), "%r is not one of %s"
                           % (value, ", ".join(repr(x) for x in schema["enum"]))))


def _const(value, schema, root, path, out):
    if value != schema["const"]:
        out.append(Problem(_where(path), "expected %r" % (schema["const"],)))


def _required(value, schema, root, path, out):
    if not isinstance(value, dict):
        return
    for name in schema["required"]:
        if name not in value:
            out.append(Problem(_where(path), "missing required property %r" % (name,)))


def _properties(value, schema, root, path, out):
    if not isinstance(value, dict):
        return
    for name, subschema in schema["properties"].items():
        if name in value:
            _check(value[name], subschema, root, "%s.%s" % (path, name), out)


def _additional_properties(value, schema, root, path, out):
    if not isinstance(value, dict) or schema["additionalProperties"] is not False:
        return
    declared = set(schema.get("properties", {}))
    for name in value:
        if name not in declared:
            # Strictness here is what stops a typo becoming a silently ignored clause: an IR
            # with `"assertions"` instead of `"assertion"` must not validate.
            out.append(Problem(_where(path), "unexpected property %r" % (name,)))


def _items(value, schema, root, path, out):
    if not isinstance(value, list):
        return
    for index, item in enumerate(value):
        _check(item, schema["items"], root, "%s[%d]" % (path, index), out)


def _min_items(value, schema, root, path, out):
    if isinstance(value, list) and len(value) < schema["minItems"]:
        out.append(Problem(_where(path), "needs at least %d item(s)" % schema["minItems"]))


def _min_properties(value, schema, root, path, out):
    if isinstance(value, dict) and len(value) < schema["minProperties"]:
        out.append(Problem(_where(path),
                           "needs at least %d propert(y/ies)" % schema["minProperties"]))


def _min_length(value, schema, root, path, out):
    if isinstance(value, str) and len(value) < schema["minLength"]:
        out.append(Problem(_where(path), "must not be empty"))


def _minimum(value, schema, root, path, out):
    if isinstance(value, (int, float)) and not isinstance(value, bool) \
            and value < schema["minimum"]:
        out.append(Problem(_where(path), "must be at least %s" % schema["minimum"]))


def _pattern(value, schema, root, path, out):
    if isinstance(value, str) and not re.search(schema["pattern"], value):
        out.append(Problem(_where(path), "%r does not match %s" % (value, schema["pattern"])))


_HANDLERS = {
    "type": lambda *a: None,          # handled ahead of the loop; listed so it is "recognised"
    "enum": _enum,
    "const": _const,
    "required": _required,
    "properties": _properties,
    "additionalProperties": _additional_properties,
    "items": _items,
    "minItems": _min_items,
    "minProperties": _min_properties,
    "minLength": _min_length,
    "minimum": _minimum,
    "pattern": _pattern,
}
