# -*- coding: utf-8 -*-
"""
PATHS - addressing a value inside a DemoPMS response.

The same job `minihotel/paths.py` does for a document tree, for a wire format that has no
attributes, no tags and no text nodes: only keys, arrays and JSON scalars.

WRITTEN FRESH RATHER THAN SHARED, ON PURPOSE. Two adapters that share a path engine share the
assumptions of whichever wire format was implemented first, and the second one then gets
described in the first one's vocabulary. The point of this provider is to prove that nothing
ABOVE the adapter had to learn what either wire format is; below the line, each says what it
actually is.

THE GRAMMAR
-----------
    path      := segment ('.' segment)*
    segment   := key | key '[]' | key '[' child '=' value ']'

    booking_ref                              a key on the object we are standing on
    total.currency                           a nested object's key
    bookings[].booking_ref                   one value per element of an array
    rooms[].limits[kind=adults].max          select an array element by a key it carries

The predicate form exists for the same reason MiniHotel's does: per-guest-type capacity
arrives as a list of objects distinguished only by a key one of them carries, and there is no
other way to say "the adult one". The comparison is against the value's string form, because a
wire format is text as far as a path is concerned.

TWO DISTINCTIONS THIS LAYER KEEPS AND DOES NOT DECIDE ABOUT
-----------------------------------------------------------
1. "No such key" is `[]`; "the key is there holding null" is `[None]`. DemoPMS writes `null`
   where MiniHotel writes `<x />`, and whether those two mean the same thing is the RESOLVER's
   decision, made per field from the registry's `absent_means`. Collapsing them here would hide
   which form the provider actually used.

2. A prefix is stripped EXPLICITLY, never guessed. MiniHotel can anchor a path by looking for
   the element's own tag, because an XML node knows what it is called. A JSON object does not:
   `{"room_no": "01"}` could be a room, an occupancy segment or a stay. So a record carries the
   path it was cut at, and `strip_prefix` answers "is this path readable from here, and as
   what?" - returning None when the answer is no. That None is R7 made structural: a stay asked
   for a path belonging to the room list is refused rather than handed a stranger's value.
"""
from __future__ import annotations

import json
import re
from typing import Any

# key, then optionally `[]` or `[child=value]`.
_SEGMENT = re.compile(r"^([A-Za-z_][\w\-]*)(?:(\[\])|\[([\w.\-]+)=([^\]]*)\])?$")


class PathError(ValueError):
    """The path or the document is malformed.

    Raised rather than returning no matches, for the reason MiniHotel's twin gives: a path that
    silently matches nothing becomes an evidence gap that blames the hotel's data for a typo in
    our own specification.
    """


def parse_document(body: str | bytes) -> Any:
    """Parse a provider response into plain Python data."""
    try:
        return json.loads(body)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise PathError("the provider response is not well-formed JSON: %s" % exc) from None


def find_all(node: Any, path: str) -> list[Any]:
    """Every JSON value this path addresses, in document order.

    An empty list means the key is not there. `[None]` means it is there and holds null - two
    different facts, and the resolver treats them differently per field.
    """
    nodes = [node]
    for key, is_array, child, wanted in _parse(path):
        nodes = _descend(nodes, key, is_array, child, wanted)
    return nodes


def strip_prefix(path: str, prefix: str) -> str | None:
    """`path` as read from a record cut at `prefix`, or None if it does not belong there.

    None is the important return. It is what stops a record resolving a path that addresses a
    different branch of the response, which is the JSON spelling of "a record may never read a
    sibling" (R7).
    """
    if not prefix:
        # A whole response, uncut, stands at the root: every path is readable from here.
        return path
    if path == prefix:
        # The record IS the value the path addresses - a folio record cut at `ledger`, asked
        # for `ledger`. Nothing left to descend through.
        return ""
    if path.startswith(prefix + "."):
        return path[len(prefix) + 1:]
    return None


# --------------------------------------------------------------------------- internals
def _descend(nodes: list[Any], key: str, is_array: bool, child: str | None,
             wanted: str | None) -> list[Any]:
    """One path step, over every node reached so far."""
    found: list[Any] = []
    for node in nodes:
        if not isinstance(node, dict) or key not in node:
            # Not an object, or the key is absent. Either way this branch addresses nothing;
            # it is not an error, because a control asks every record for every field and
            # "this record does not carry it" is the ordinary case.
            continue
        value = node[key]
        if not (is_array or child is not None):
            found.append(value)
            continue
        if not isinstance(value, list):
            # The path says this is a list and the response says it is not. Addressing nothing
            # is right: a wire format that changed shape must not be read as if it had not.
            continue
        for element in value:
            if child is None:
                found.append(element)
            elif isinstance(element, dict) and str(element.get(child)) == wanted:
                found.append(element)
    return found


def _parse(path: str) -> list[tuple[str, bool, str | None, str | None]]:
    text = (path or "").strip()
    if not text:
        raise PathError("an empty path addresses nothing")

    steps: list[tuple[str, bool, str | None, str | None]] = []
    for segment in text.split("."):
        match = _SEGMENT.match(segment.strip())
        if match is None:
            raise PathError(
                "%r is not a valid path segment in %r - expected key, key[] or key[child=value]"
                % (segment, path))
        key, array, child, wanted = match.groups()
        steps.append((key, array is not None, child, wanted))
    return steps
