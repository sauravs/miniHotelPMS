# -*- coding: utf-8 -*-
"""
PATHS - addressing a value inside a provider response, structurally.

This module is the fix for review finding F4, and it is worth understanding what it replaces.

v1 addressed all 52 field mappings with REGEXES over the raw response text. Two failures were
reproduced against the v1 resolver before a line of this was written:

    attrs as captured | arrival = known('2026-07-01' date)
    attrs reordered   | arrival = unknown(reservation.arrival_date is absent...)
    escaped surname   | known('O&apos;Brien &amp; Sons')

The first is the dangerous one. `reservation.arrival_date` mapped to `<Timespan arrival="..."`,
which requires `arrival` to be the FIRST attribute - and XML attribute order is explicitly not
significant, so a vendor is free to change it without notice. Note how it failed: not with an
exception but as an evidence gap, which in a scope predicate means the control silently stops
applying to records it should be judging.

The provider map already recorded a structured `path` for every field. v1 never executed it.

THE GRAMMAR
-----------
    path      := segment ('/' segment)* ('@' attribute)?
    segment   := name ('[' child '=' value ']')?

    Booking@Status                                  an attribute of the record element itself
    Booking/ResGlobalInfo/Timespan@arrival          a nested element's attribute
    PrimaryGuest/Email                              an element's text
    rec_rooms_gst_max[rgm_gst_type=A]/rgm_max       select by a child element's text

The predicate form exists because MiniHotel stores per-guest-type capacity as three sibling
blocks distinguished only by a child element's value - there is no other way to say "the adult
one".

WHAT THIS LAYER DOES NOT DECIDE
-------------------------------
It returns raw strings, and it distinguishes "no such node" (an empty list) from "the node is
there and holds an empty string" ([""]). MiniHotel writes both `rateCode=""` and
`<rm_clsdt1 />`, and whether those mean the same thing is the RESOLVER's decision, made per
field from the registry's `absent_means`. Collapsing them here would hide which form the
provider actually used.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Iterable

_SEGMENT = re.compile(r"^([A-Za-z_][\w.\-]*)(?:\[([\w.\-]+)=([^\]]*)\])?$")


class PathError(ValueError):
    """The path or the document is malformed.

    Raised rather than returning no matches, and the distinction is the whole point: a path
    that silently matches nothing becomes an evidence gap that blames the hotel's data for a
    typo in our own specification.
    """


def parse_document(xml: str | bytes) -> ET.Element:
    """Parse a provider response into a tree, with namespaces flattened.

    Namespace stripping is deliberate. The captures declare `xsd` and `xsi` prefixes without
    using them, so every element is currently unqualified - but a provider that started
    emitting a default namespace would silently break all 52 paths at once, and the paths in
    `spec/providers/*.json` describe a shape rather than a namespace URI.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise PathError("the provider response is not well-formed XML: %s" % exc) from None
    for element in root.iter():
        if isinstance(element.tag, str) and element.tag.startswith("{"):
            element.tag = element.tag.split("}", 1)[1]
        for name in [k for k in element.attrib if k.startswith("{")]:
            element.attrib[name.split("}", 1)[1]] = element.attrib.pop(name)
    return root


def find_elements(element: ET.Element, path: str) -> list[ET.Element]:
    """Every ELEMENT this path addresses, in document order.

    The record layer needs this: cutting a response into records is selecting elements, not
    reading values, and it uses exactly the same grammar so a record boundary and a field path
    cannot drift apart in how they are written.
    """
    steps, attribute = _parse(path)
    if attribute is not None:
        raise PathError("%r addresses an attribute, which is a value rather than an element"
                        % (path,))
    nodes: list[ET.Element] = [element]
    for name, child_name, child_value in steps:
        nodes = list(_descend(nodes, name, child_name, child_value))
    return nodes


def anchor(path: str, tag: str) -> str:
    """Trim a path so it starts at the element the caller is standing on.

    Paths in the provider map are written relative to the RESPONSE - `Reservations/Reservation
    @ResNumber` - but records are cut deeper: an occupancy record IS a `<Reservation>`. Without
    trimming, that path looks for a `Reservations` inside a `Reservation` and finds nothing,
    which surfaces as an evidence gap rather than as the addressing mistake it is.

    The rule: if any segment names the element we are standing on, drop everything before it.
    `iter()` includes the element itself, so the segment then matches where we are. If no
    segment matches, the path is used whole and descends from here - which is the right answer
    for `PrimaryGuest/Email` read from a `<Booking>`.
    """
    steps, attribute = _parse(path)
    names = [name for name, _, _ in steps]
    if tag in names:
        index = len(names) - 1 - names[::-1].index(tag)
        if index:
            trimmed = path.split("@")[0].split("/")[index:]
            return "/".join(trimmed) + (("@" + attribute) if attribute else "")
    return path


def find_all(element: ET.Element, path: str) -> list[str]:
    """Every raw string this path addresses, in document order.

    An empty list means the node is not there. `[""]` means it is there and holds nothing -
    two different facts, and the resolver treats them differently per field.
    """
    steps, attribute = _parse(path)
    nodes: list[ET.Element] = [element]
    for name, child_name, child_value in steps:
        nodes = list(_descend(nodes, name, child_name, child_value))

    if attribute is None:
        # `.text` is None for `<x />` and for `<x></x>` alike; both mean "present, empty".
        return [(node.text or "") for node in nodes]
    return [node.attrib[attribute] for node in nodes if attribute in node.attrib]


def _descend(nodes: Iterable[ET.Element], name: str, child_name: str | None,
             child_value: str | None) -> Iterable[ET.Element]:
    """One path step, over every node reached so far.

    `Element.iter(name)` includes the element itself when its tag matches, which is exactly
    what the first step needs: for a `reservation` record the element IS the `Booking`, and
    `Booking@Status` has to address it rather than look for a `Booking` inside it.
    """
    seen: set[int] = set()
    for node in nodes:
        for candidate in node.iter(name):
            if id(candidate) in seen:
                continue
            if child_name is not None:
                child = candidate.find(child_name)
                if child is None or (child.text or "").strip() != child_value:
                    continue
            seen.add(id(candidate))
            yield candidate


def _parse(path: str) -> tuple[list[tuple[str, str | None, str | None]], str | None]:
    text = (path or "").strip()
    if not text:
        raise PathError("an empty path addresses nothing")

    attribute: str | None = None
    if "@" in text:
        text, _, attribute = text.partition("@")
        if not attribute.strip():
            raise PathError("%r ends in @ with no attribute name" % (path,))
        attribute = attribute.strip()
    if not text.strip():
        raise PathError("%r names an attribute but no element" % (path,))

    steps: list[tuple[str, str | None, str | None]] = []
    for segment in text.split("/"):
        match = _SEGMENT.match(segment.strip())
        if match is None:
            raise PathError(
                "%r is not a valid path segment in %r - expected Name or Name[child=value]"
                % (segment, path))
        name, child_name, child_value = match.groups()
        steps.append((name, child_name, child_value))
    return steps, attribute
