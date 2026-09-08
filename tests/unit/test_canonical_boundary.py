# -*- coding: utf-8 -*-
"""
Success criterion 5: no PMS identifier appears above the provider adapter.

This is the whole PMS-agnostic thesis, made mechanical. A rule that named `TotalDebit` could
not run on a second system, so the promise is only as good as the enforcement - and the
enforcement is a grep, deliberately strict enough to catch PROSE. It caught comments twice in
v1, which is the correct outcome: a comment explaining what `Booking@Status` maps to is a sign
that the knowledge has leaked upwards even if the code has not.

The one deliberate exception is `Value.source`, which carries a string like
`pms:minihotel/GetReservationBalance`. It crosses as DATA rather than as an identifier - an
auditor has to know which system and which call produced a number - and no PMS FIELD PATH is in
it, and no layer above ever parses it.
"""
import ast
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[2] / "hotelcontrols"

# Where MiniHotel is allowed to exist. Everything else in the tree must be able to run against
# a PMS nobody has written an adapter for yet.
ALLOWED = ("providers/minihotel",)

# Endpoint names, wire-format field paths and vendor spellings. If one of these appears above
# the adapter, something that should have been canonical is not.
PMS_IDENTIFIERS = (
    "GetReservationKey", "GetReservationBalance", "RoomStatusInquiry", "getRoomTypes",
    "getRooms", "BulkARI", "TotalDebit", "Minihotel_reservation_id", "Portal_reservation_id",
    "rnm_struct_room", "rm_clsdt", "RoomStay", "AmountAfterTaxes", "rec_rooms_gst_max",
    "createDateTime", "isGroupReservation", "mealStatus", "roomTypeID", "AvailRaters",
)


def engine_files():
    for path in sorted(ENGINE.rglob("*.py")):
        relative = path.relative_to(ENGINE).as_posix()
        if any(relative.startswith(allowed) for allowed in ALLOWED):
            continue
        yield relative, path


def test_there_are_files_above_the_boundary_to_check():
    """A guard on the test below: an empty generator would pass it vacuously."""
    assert len(list(engine_files())) >= 10


@pytest.mark.parametrize("identifier", PMS_IDENTIFIERS)
def test_no_pms_identifier_appears_above_the_provider_adapter(identifier):
    offenders = []
    for relative, path in engine_files():
        text = path.read_text(encoding="utf-8")
        if identifier in text:
            line = next(i + 1 for i, l in enumerate(text.splitlines()) if identifier in l)
            offenders.append("%s line %d" % (relative, line))
    assert not offenders, (
        "%r is MiniHotel's vocabulary and must not appear above providers/minihotel/: %s"
        % (identifier, offenders))


def test_the_vendor_is_never_named_in_code_above_the_boundary():
    """The vendor's NAME may appear in prose - explaining honestly why a rule exists requires
    saying which system the finding came from, and "reservation 007003199 reports 870 USD while
    its own folio reports 3262.5 ILS" is the best comment in the kernel.

    What must never appear is the name in code the engine EVALUATES: a string literal, an
    attribute, a branch. That would be a layer deciding something based on which PMS answered.
    Checked with `ast`, with docstrings excluded, so the test constrains behaviour rather than
    vocabulary. (Wire-format identifiers are stricter - the test above bans those in prose too,
    because citing a finding never requires naming a vendor's field path.)
    """
    offenders = []
    for relative, path in engine_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value) for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in docstrings and "minihotel" in node.value.lower():
                offenders.append("%s line %d: %r" % (relative, node.lineno, node.value[:60]))
            if isinstance(node, (ast.Name, ast.Attribute)):
                name = node.id if isinstance(node, ast.Name) else node.attr
                if "minihotel" in name.lower():
                    offenders.append("%s line %d: %s" % (relative, node.lineno, name))
    assert not offenders, offenders
