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

Since slice 7 there are two adapters, and BOTH are policed. That symmetry is the point: a
boundary enforced against one vendor's vocabulary and not another's is not a boundary, it is a
grudge. The second provider is the one that would slip, because it is ours.
"""
import ast
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[2] / "hotelcontrols"

# Where an adapter is allowed to exist: its OWN directory, and nowhere else. Discovered rather
# than listed, so a third PMS is covered by this test from the moment it is added - a hand-kept
# list would let the newest adapter be the unguarded one, which is the shape of issue #9.
ALLOWED = tuple("providers/%s" % path.name
                for path in sorted((ENGINE / "providers").iterdir())
                if path.is_dir() and (path / "adapter.py").is_file())

# Endpoint names, wire-format field paths and vendor spellings, FROM EVERY PROVIDER. If one of
# these appears above the adapters, something that should have been canonical is not.
#
# The second provider's identifiers are here for the same reason the first one's are, and the
# fact that it is fictional makes no difference: a boundary policed in one direction is not a
# boundary. `bookings`, `rooms` and `ledger` are its endpoint names; `booking_ref`, `room_no`
# and the rest are its field paths.
PMS_IDENTIFIERS = (
    "GetReservationKey", "GetReservationBalance", "RoomStatusInquiry", "getRoomTypes",
    "getRooms", "BulkARI", "TotalDebit", "Minihotel_reservation_id", "Portal_reservation_id",
    "rnm_struct_room", "rm_clsdt", "RoomStay", "AmountAfterTaxes", "rec_rooms_gst_max",
    "createDateTime", "isGroupReservation", "mealStatus", "roomTypeID", "AvailRaters",
    "booking_ref", "room_no", "room_class", "out_of_service", "postings", "external_ref",
    "card_last4", "group_booking", "demopms/v1",
)

# The vendor names themselves, in code the engine evaluates. Taken from the provider registry,
# so this cannot fall out of date either.
VENDOR_NAMES = tuple(path.name for path in sorted((ENGINE / "providers").iterdir())
                     if path.is_dir() and (path / "adapter.py").is_file())


def engine_files():
    for path in sorted(ENGINE.rglob("*.py")):
        relative = path.relative_to(ENGINE).as_posix()
        if any(relative.startswith(allowed) for allowed in ALLOWED):
            continue
        yield relative, path


def test_there_are_files_above_the_boundary_to_check():
    """A guard on the tests below: an empty generator would pass them vacuously."""
    assert len(list(engine_files())) >= 10


def test_more_than_one_adapter_is_being_policed():
    """The other guard, and the one this slice adds. With a single adapter the boundary is
    untestable in principle: everything above it is portable to a PMS nobody has tried."""
    assert len(ALLOWED) >= 2, ALLOWED
    assert len(VENDOR_NAMES) == len(ALLOWED)


@pytest.mark.parametrize("identifier", PMS_IDENTIFIERS)
def test_no_pms_identifier_appears_above_the_provider_adapter(identifier):
    offenders = []
    for relative, path in engine_files():
        text = path.read_text(encoding="utf-8")
        if identifier in text:
            line = next(i + 1 for i, l in enumerate(text.splitlines()) if identifier in l)
            offenders.append("%s line %d" % (relative, line))
    assert not offenders, (
        "%r is one provider's own vocabulary and must not appear outside %s: %s"
        % (identifier, " or ".join(ALLOWED), offenders))


def test_the_vendor_is_never_named_in_code_above_the_boundary():
    """The vendor's NAME may appear in prose - explaining honestly why a rule exists requires
    saying which system the finding came from, and "reservation 007003199 reports 870 USD while
    its own folio reports 3262.5 ILS" is the best comment in the kernel.

    What must never appear is the name in code the engine EVALUATES: a string literal, an
    attribute, a branch. That would be a layer deciding something based on which PMS answered.
    Checked with `ast`, with docstrings excluded, so the test constrains behaviour rather than
    vocabulary. (Wire-format identifiers are stricter - the test above bans those in prose too,
    because citing a finding never requires naming a vendor's field path.)

    Checked for EVERY registered provider, including the fictional one. A boundary policed in
    one direction is not a boundary, and the second adapter is the one that would slip: it is
    ours, so there is no vendor to be embarrassed in front of.
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
                    and id(node) not in docstrings:
                for vendor in VENDOR_NAMES:
                    if vendor in node.value.lower():
                        offenders.append("%s line %d: %r"
                                         % (relative, node.lineno, node.value[:60]))
            if isinstance(node, (ast.Name, ast.Attribute)):
                name = (node.id if isinstance(node, ast.Name) else node.attr).lower()
                for vendor in VENDOR_NAMES:
                    if vendor in name or vendor.replace("pms", "") + "pms" in name:
                        offenders.append("%s line %d: %s" % (relative, node.lineno, name))
    assert not offenders, offenders
