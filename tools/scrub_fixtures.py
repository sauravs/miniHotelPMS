# -*- coding: utf-8 -*-
"""
Pseudonymise a captured provider response so it can be committed.

    python3 -m tools.scrub_fixtures <raw-capture> <output>
    python3 -m tools.scrub_fixtures --all            # rebuild every fixture from raw/

Decision D6. This repository is public and the captures came off MiniHotel's sandbox carrying
third-party guest data: 27 distinct email addresses and 30 phone numbers across the 2026
capture, several not obviously test data, plus free-text remarks naming a guest and describing
a manager's approval. That is someone else's personal data in someone else's system.

WHAT IS AND IS NOT TOUCHED
--------------------------
Removed: names, email addresses, phone and fax numbers, identity-document numbers, street
addresses, the name on a payment card, and free-text remarks.

Kept EXACTLY: reservation ids, room numbers, statuses, dates, amounts, currencies, guest
counts, rate codes, room types, and every structural quirk. Those are the evidence. A scrubber
that adjusted a balance or a status would be rewriting the answer, and every finding this
project has came from a format rather than from a person's name.

THREE PROPERTIES THE TEST SUITE DEPENDS ON
------------------------------------------
  Deterministic          same input, same output, always. Fixtures stay byte-stable, diffs
                         stay readable, and one guest stays one guest across two reservations -
                         which a duplicate-detection control would otherwise see differently.
  Structure-preserving   an email still looks like an email; a phone keeps its length and stays
                         numeric.
  Presence-preserving    THE subtle one. Control 15 asserts `reservation.guest.email exists`.
                         Filling a blank field would turn a FAIL into a PASS and blanking a
                         filled one would do the reverse, so empty stays empty and non-empty
                         stays non-empty, unconditionally.

The pseudonyms are derived with a keyed hash over the original value. The key is a constant in
this file rather than a secret: the point is stable fake data, not confidentiality of the
mapping - the raw captures never leave the machine that made them, and are git-ignored.
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

# Not a secret. It exists so that two different KINDS of field with the same spelling - a
# surname and a city, say - do not collapse to the same token and invent a relationship that
# was never in the data.
_SALT = "minihotelpms-fixture-pseudonym-v2"

# Pools chosen to be obviously fictional. Nobody should be able to mistake a fixture for a real
# guest list, which is half the point of scrubbing it in the first place.
_GIVEN = ("Ada", "Bruno", "Cora", "Dmitri", "Elena", "Farid", "Greta", "Hugo", "Iris",
          "Janek", "Kira", "Luca", "Mira", "Nils", "Ombra", "Pavel", "Quinn", "Rosa",
          "Sten", "Tova", "Uma", "Vidal", "Wren", "Xenia", "Yara", "Zoltan")
_SURNAME = ("Almeida", "Berger", "Costa", "Duarte", "Eriksen", "Ferrer", "Grimaldi", "Halvorsen",
            "Ionescu", "Jansen", "Kowalski", "Lindqvist", "Moreau", "Novak", "Olsen", "Petrov",
            "Quintero", "Rasmussen", "Sorokin", "Torres", "Ueda", "Vargas", "Wexler", "Ximenes",
            "Yilmaz", "Zavala")
_CITY = ("Northmoor", "Eastbourne Vale", "Westhaven", "Southgate", "Lakemont", "Rivermead",
         "Fairholm", "Brookmere")
_STREET = ("Cedar Lane", "Harbour Way", "Mill Road", "Orchard Street", "Quarry Rise",
           "Tanner Walk")

# Free text is replaced wholesale rather than word by word. The remarks fields are where a
# manager wrote an approval in prose, and no field-level rule can reliably find a name inside
# a sentence in a language the rest of the system does not speak. Nothing reads remarks today
# (open question 1.5); if that changes, this placeholder needs revisiting rather than trusting.
_REMARK = "[remark redacted for publication - see tools/scrub_fixtures.py]"


def _digest(value: str, kind: str) -> int:
    return int(hashlib.sha256(("%s|%s|%s" % (_SALT, kind, value)).encode("utf-8")).hexdigest()
               [:12], 16)


def _pick(pool: tuple[str, ...], value: str, kind: str) -> str:
    return pool[_digest(value, kind) % len(pool)]


def scrub_text(value: str, kind: str) -> str:
    """One value's pseudonym. Empty in, empty out - always (presence preservation)."""
    if not (value or "").strip():
        return value

    if kind == "given_name":
        return _pick(_GIVEN, value, kind)
    if kind == "surname":
        return _pick(_SURNAME, value, kind)
    if kind == "name_on_card":
        return "%s %s" % (_pick(_GIVEN, value, kind).upper(),
                          _pick(_SURNAME, value, kind).upper())
    if kind == "email":
        # `.example` is reserved by RFC 2606 precisely so it can never route anywhere.
        return "%s.%s@example.example" % (_pick(_GIVEN, value, kind).lower(),
                                          _pick(_SURNAME, value, kind).lower())
    if kind in ("phone", "id_number"):
        # Length is preserved because the formats are the evidence - an Israeli mobile that
        # stops looking like one stops exercising whatever reads it. A leading zero is kept
        # when the original had one, for the same reason.
        digits = str(_digest(value, kind)).ljust(len(value), "0")[:len(value)]
        if value.strip().startswith("0") and len(digits) > 1:
            digits = "0" + digits[1:]
        return digits
    if kind == "city":
        return _pick(_CITY, value, kind)
    if kind == "street":
        return "%d %s" % (_digest(value, kind) % 90 + 1, _pick(_STREET, value, kind))
    if kind == "zip":
        return str(_digest(value, kind)).ljust(len(value), "0")[:len(value)]
    if kind == "free_text":
        return _REMARK
    raise ValueError("no pseudonymisation rule for field kind %r" % (kind,))


# What to scrub, as (element path, attribute or None, kind). Paths are matched anywhere in the
# document. Anything not listed here is left EXACTLY as captured.
_ATTRIBUTES = (
    ("Name", "givenName", "given_name"),
    ("Name", "surname", "surname"),
    ("CreditCard", "NameOnCard", "name_on_card"),
    ("Address", "Street", "street"),
    ("Address", "City", "city"),
    ("Address", "Zip", "zip"),
)
_ELEMENTS = (
    ("Email", "email"),
    ("Phone", "phone"),
    ("Fax", "phone"),
    ("IdNumber", "id_number"),
    ("PrintedRemarks", "free_text"),
    ("NonPrintedRemarks", "free_text"),
    ("SpecialRequest", "free_text"),
    ("HouseKeepingRemarks", "free_text"),
)


def scrub_xml(xml: str) -> str:
    """Pseudonymise one captured XML response, preserving everything the engine reads."""
    # The XML declaration and any leading whitespace are preserved by hand: ElementTree does
    # not round-trip them, and a fixture whose first line changed would produce a noisy diff
    # for a reason unrelated to its content.
    declaration = ""
    match = re.match(r"^\s*<\?xml[^>]*\?>\s*", xml)
    if match:
        declaration = match.group(0)

    root = ET.fromstring(xml)
    for element in root.iter():
        tag = element.tag.split("}")[-1]          # tolerate a namespaced document
        for name, attribute, kind in _ATTRIBUTES:
            if tag == name and attribute in element.attrib:
                element.set(attribute, scrub_text(element.get(attribute, ""), kind))
        for name, kind in _ELEMENTS:
            if tag == name:
                element.text = scrub_text(element.text or "", kind)
    body = ET.tostring(root, encoding="unicode")
    return declaration + body if declaration else body


# --------------------------------------------------------------------------- CLI
ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "fixtures" / "minihotel" / "raw"
OUT = ROOT / "fixtures" / "minihotel"


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--all":
        if not RAW.is_dir():
            print("no raw captures at %s - nothing to rebuild" % RAW)
            return 0
        count = 0
        for source in sorted(RAW.glob("*.xml")):
            target = OUT / source.name
            target.write_text(scrub_xml(source.read_text(encoding="utf-8")), encoding="utf-8")
            print("scrubbed %s -> %s" % (source.name, target.relative_to(ROOT)))
            count += 1
        print("\n%d fixture(s) rebuilt. Raw captures stay in %s and are git-ignored."
              % (count, RAW.relative_to(ROOT)))
        return 0

    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2])
        print(__doc__.strip().splitlines()[3])
        return 2

    source, target = pathlib.Path(argv[0]), pathlib.Path(argv[1])
    target.write_text(scrub_xml(source.read_text(encoding="utf-8")), encoding="utf-8")
    print("scrubbed %s -> %s" % (source, target))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
