# -*- coding: utf-8 -*-
"""
TRANSCODE - the same hotel, in the other wire format.

    python3 -m tools.transcode_demopms            rewrite fixtures/demopms/
    python3 -m tools.transcode_demopms --check    verify a rebuild changes nothing

Success criterion 7 asks that the same IR, over the same logical hotel, through two providers,
yields the same verdicts. "The same hotel" has to mean something, or the claim is decoration -
and hand-writing a second set of fixtures is precisely how it would stop meaning anything. Give
a person a blank file and the eleven controls they are about to run against it, and the fixtures
drift towards the answers that look best. v1 shipped `fixtures/synthetic/` for exactly that
reason and reached outcomes its captures could not.

So this tool reads the vendor captures and re-encodes them, field by field, into DemoPMS's wire
format. Same 138 reservations. Same 28 rooms. Same five folios. Same two occupancy segments.
Same evidence gaps, including the ones that are inconvenient: the folios that were never
captured stay uncaptured, the statuses nobody can name stay unnameable, and the 23 rooms with
no configured capacity stay unconfigured.

DRIVEN BY THE TWO MAPPING FILES, NOT BY A HAND-WRITTEN LIST
------------------------------------------------------------
For each canonical field both providers map, this reads the RAW value at MiniHotel's path and
writes it at DemoPMS's, converting through the quirk each side declares. Nothing here knows
what any particular field is - which means the two mapping files cannot drift apart from the
fixtures without a rebuild failing.

WHY THE RAW VALUE AND NOT THE CANONICAL ONE
--------------------------------------------
Because the canonical value has already had the quirks resolved out of it, and the quirks are
the thing being transcoded. Reading `reservation.status` canonically gives UNKNOWN for `OK4`;
what has to survive into the other format is that the property uses a code nobody documented,
so `OK4` becomes `PROV4` and is left out of the demo tenant's status map too. Reading
`room.max_guests.adults` canonically gives UNKNOWN for a capacity of 0; what has to survive is
"never configured", which this format spells `-1`.

THE ONE THING THIS TOOL MAY NEVER DO is make the demo hotel answer a question the captured one
cannot. Every rule below is a re-encoding; there is no default, no fill-in and no fallback that
invents a value. A code this tool has not been told how to translate stops it.
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

from hotelcontrols.providers.base import Request
from hotelcontrols.providers.demopms.paths import strip_prefix
from hotelcontrols.providers.minihotel import FrozenSource, MiniHotelAdapter
from hotelcontrols.providers.minihotel.paths import find_all, find_elements
from hotelcontrols.providers.minihotel.records import Record as SourceRecord
from hotelcontrols.spec import TenantConfig

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "fixtures" / "minihotel"
TARGET_DIR = ROOT / "fixtures" / "demopms"
SPEC = ROOT / "spec"

# ---------------------------------------------------------------------------- vocabularies
#
# Raw code to raw code. NOT to a canonical status: the demo property's status map is a separate
# decision recorded in `spec/tenants/demo.json`, and the codes it deliberately leaves out are
# the same ones the real property leaves out. That is what keeps the two hotels the same hotel.
# `OK4` covers 32 reservations and `WL` 12 - one in five of everything we have ever seen - and
# neither is documented anywhere, so neither may quietly acquire a meaning here.
STATUS = {
    "OK": "BOOKED",
    "IN": "IN_HOUSE",
    "OUT": "DEPARTED",
    "CL": "VOID",
    "OK4": "PROV4",
    "WL": "HOLD",
    "LWP": "NOPAY",
}

# Folio posting categories, likewise raw to raw. The demo tenant's department map ships EMPTY,
# exactly as the real one does: there is no provider-wide vocabulary for these on any PMS, so
# every department is UNKNOWN until a hotel supplies its own.
DEPARTMENT = {"RMS": "ROOM_REVENUE", "CASH": "CASH_RECEIPT"}

# Where a money field's currency comes from ON THE SOURCE SIDE. This table is the transcoding
# of R9 itself: MiniHotel keeps the currency in a different part of the response from the
# amount, DemoPMS keeps them together, and this is the join between the two.
MONEY_CURRENCY = {
    "reservation.total_amount": "reservation.currency",
    "stay.amount": "reservation.currency",
    "folio.balance_due": "folio.currency",
    "folio.total_charged": "folio.currency",
    "folio.total_paid": "folio.currency",
    "folio.transactions[].amount": "folio.currency",
}

ENDPOINTS = {
    "GetReservationKey": "bookings",
    "getRooms": "rooms",
    "getRoomTypes": "room-types",
    "GetReservationBalance": "ledger",
    "RoomStatusInquiry": "occupancy",
}

# Request filter names, translated. DemoPMS spells every window one way and in lower case; the
# real provider spells it `From`/`To` on the booking filters and `from`/`to` on the occupancy
# one, in the same API.
FILTERS = {
    "ArrivalDate": "arrival",
    "DepartureDate": "departure",
    "CreateDate": "created",
    "DateRange": "window",
    "IncludeRoomPrices": "include_prices",
    "ReservationNumber": "booking_ref",
}

CAPTURES = {"sandbox2024": "demo2024", "sandbox2026": "demo2026"}

# Source fixture -> the file it becomes. Explicit, because a derived name would change silently
# the day somebody renames a capture, and these names appear in the provider map's `probe`.
FILES = {
    "1_getRoomTypes.xml": "room-types.json",
    "2_getRooms_all.xml": "rooms.json",
    "3_GetReservationKey.xml": "bookings_2024-08.json",
    "4_RoomStatus.xml": "occupancy.json",
    "9_departures_2026-07.xml": "bookings_2026-07.json",
    "5_balance_007003199.xml": "ledger_007003199.json",
    "5_balance_007003204.xml": "ledger_007003204.json",
    "5_balance_007004348.xml": "ledger_007004348.json",
    "5_balance_007004351.xml": "ledger_007004351.json",
    "5_balance_007004354.xml": "ledger_007004354.json",
}

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class Unencodable(Exception):
    """A value this tool has not been told how to translate.

    It stops the build rather than passing something plausible through. A capture that starts
    carrying a new status code must be a decision somebody makes, not a silent widening of what
    the demo hotel appears to know.
    """


# ---------------------------------------------------------------------------- the tool
class Transcoder:
    """Reads MiniHotel's raw values through its own paths; writes DemoPMS's shapes."""

    def __init__(self, spec_dir: pathlib.Path = SPEC) -> None:
        self.tenant = TenantConfig.load("sandbox", spec_dir)
        self.demo = {m["canonical"]: m for m in json.loads(
            (spec_dir / "providers" / "demopms.json").read_text(encoding="utf-8"))["mappings"]}
        self.source_index = json.loads(
            (SOURCE_DIR / "index.json").read_text(encoding="utf-8"))
        # One adapter per capture, because the source of a response is capture-scoped. The
        # 2026 capture is used for the shared responses; either would give the same bytes.
        self.adapters = {name: MiniHotelAdapter(self.tenant, FrozenSource(name, SOURCE_DIR))
                         for name in CAPTURES}

    # ------------------------------------------------------------------ documents
    def document(self, entry: dict[str, Any]) -> dict[str, Any]:
        """One source response, as the DemoPMS response it becomes."""
        capture = entry["captures"][0]
        adapter = self.adapters[capture]
        response = adapter.fetch(Request(entry["endpoint"], entry["request"]))
        endpoint = ENDPOINTS[entry["endpoint"]]

        body = {"schema": "demopms/v1", "endpoint": endpoint}
        body.update(getattr(self, "_" + endpoint.replace("-", "_"))(adapter, response))
        return body

    def _bookings(self, adapter, response) -> dict[str, Any]:
        bookings = []
        for booking in adapter.records(response, "reservation"):
            record = self._object(adapter, booking, "bookings[]", skip="bookings[].stays[]")
            record["stays"] = [
                self._object(adapter, stay, "bookings[].stays[]")
                for stay in self._stays_of(booking)]
            bookings.append(record)
        return {"bookings": bookings}

    def _rooms(self, adapter, response) -> dict[str, Any]:
        return {"rooms": [self._object(adapter, room, "rooms[]")
                          for room in adapter.records(response, "room")]}

    def _room_types(self, adapter, response) -> dict[str, Any]:
        return {"room_types": [self._object(adapter, kind, "room_types[]")
                               for kind in adapter.records(response, "room_type")]}

    def _ledger(self, adapter, response) -> dict[str, Any]:
        folio = adapter.records(response, "folio")[0]
        # The booking this ledger belongs to. Read structurally rather than through a canonical
        # field, because none maps here: `reservation.id` is declared to come from the booking
        # call, and a ledger is fetched BY that id rather than reporting it as evidence. The
        # demo response echoes it the way a real one would, and the fixture index keys on it.
        echoed = find_all(folio.element, "ReservationNumber")
        ledger = {"booking_ref": echoed[0] if echoed else None}
        ledger.update(self._object(adapter, folio, "ledger", skip="ledger.postings[]"))
        ledger["postings"] = [
            self._object(adapter, posting, "ledger.postings[]", currency_from=folio)
            for posting in adapter.records(response, "folio_transaction")]
        return {"ledger": ledger}

    def _occupancy(self, adapter, response) -> dict[str, Any]:
        """The nested quirk, assembled. Segments are grouped under the room they name, in the
        order the rooms first appear - so the transcode is deterministic without sorting, and
        the segment order within a room is the source document's."""
        rooms: dict[str, dict[str, Any]] = {}
        for segment in adapter.records(response, "occupancy"):
            number = self._raw(adapter, "occupancy.room_number", segment)
            if number is None:
                raise Unencodable(
                    "an occupancy segment with no room number cannot be nested under a room - "
                    "this wire format has nowhere else to put it")
            room = rooms.setdefault(number, {"room_no": number, "occupancy": []})
            room["occupancy"].append(
                self._object(adapter, segment, "rooms[].occupancy[]"))
        return {"rooms": list(rooms.values())}

    # ------------------------------------------------------------------ one record
    def _object(self, adapter, record, prefix: str, skip: str | None = None,
                currency_from=None) -> dict[str, Any]:
        """Every canonical field whose DemoPMS path sits under `prefix`, encoded.

        Driven by the mapping file, so a field added to either provider map without the other
        shows up as a rebuild difference rather than as a fixture that quietly says less.
        """
        built: dict[str, Any] = {}
        for canonical, mapping in self.demo.items():
            path = mapping["path"]
            if skip and path.startswith(skip):
                continue
            relative = strip_prefix(path, prefix)
            if relative is None or relative == "":
                continue
            raw = self._raw(adapter, canonical, record)
            if raw is _ABSENT:
                # Absent stays absent. The registry decides what that means per field, and it
                # is not always "unknown" - a missing email is the signal control 15 looks for.
                continue
            _set(built, relative, self._encode(adapter, canonical, mapping, raw,
                                               record, currency_from))
        return built

    def _raw(self, adapter, canonical: str, record) -> Any:
        """MiniHotel's raw string for one canonical field on one record, or the absent marker.

        Reads through the source adapter's own path machinery rather than a second
        implementation of it, so the transcode cannot disagree with the resolver about where a
        value lives - which would produce a demo hotel that is subtly not this hotel.
        """
        mapping = adapter.mappings.get(canonical)
        if mapping is None:
            return _ABSENT
        if record.endpoint != mapping["endpoint"]:
            return _ABSENT
        for element in record.lineage:
            found = adapter._extract(mapping, element)
            if found:
                return found[0]
        return _ABSENT

    # ------------------------------------------------------------------ one value
    def _encode(self, adapter, canonical: str, mapping: dict[str, Any], raw: str,
                record, currency_from) -> Any:
        """One raw MiniHotel value, in DemoPMS's spelling of the same fact."""
        transform = mapping["transform"]
        text = (raw or "").strip()

        if not text:
            # Present but empty. Both formats can say this; they spell it differently, and the
            # registry decides per field what it implies.
            return None

        if transform == "date_dmy_to_iso":
            return self._date(adapter, canonical, text)
        if transform == "tenant_status_map":
            return _translate(STATUS, text, "status")
        if transform == "tenant_department_map":
            return _translate(DEPARTMENT, text, "folio department")
        if transform == "money_object":
            return self._money(adapter, canonical, text, record, currency_from)
        if transform == "sentinel_is_unknown":
            # The R12 transcode. 0 means "nobody configured this" on the source provider and
            # therefore must not arrive here as a real zero - this format keeps 0 for a room
            # that genuinely sleeps nobody, and spends -1 on the gap.
            return -1 if _int(canonical, text) == 0 else _int(canonical, text)
        if transform == "to_int":
            return _int(canonical, text)
        if transform == "json_bool":
            return _bool(canonical, text)
        if transform == "clean_soiled":
            return _translate({"C": "CLEAN", "D": "SOILED"}, text.upper(), "housekeeping status")
        if transform == "charge_payment":
            return _translate({"1": "CHARGE", "2": "PAYMENT"}, text, "posting direction")
        # `casefold`, `presence_bool` and the untransformed fields all carry the text through.
        # Case is preserved deliberately: the room-type codes differ in case between MiniHotel
        # endpoints (R13), and flattening that here would hide it from the demo hotel too.
        return raw

    def _date(self, adapter, canonical: str, text: str) -> str | None:
        """A source date in whichever of the three formats that field uses, as `08 Jul 2026`.

        Parsed through the source provider's own transform. A date it refuses is written as
        null rather than guessed at, so it resolves UNKNOWN on both providers - which is the
        only honest transcode of "this value is not a date".
        """
        parsed = adapter._transform(adapter.mappings[canonical], text, None)
        if not parsed.is_known:
            return None
        year, month, day = parsed.payload.split("-")
        return "%02d %s %s" % (int(day), MONTHS[int(month) - 1], year)

    def _money(self, adapter, canonical: str, text: str, record, currency_from) -> dict:
        """An amount and the currency it is denominated in, joined into one object (R9).

        The currency is read from wherever the SOURCE provider keeps it - a different part of
        the response, and not the same part for every field. Reservation 007003199 reports 870
        USD while its own folio reports 3262.5 ILS, and that split has to survive into a format
        where the two travel together, or the demo hotel would be a hotel with one currency.
        """
        holder = currency_from if currency_from is not None else record
        currency = self._raw(adapter, MONEY_CURRENCY[canonical], holder)
        currency = None if currency is _ABSENT or not str(currency).strip() else currency

        if adapter.mappings[canonical]["transform"] == "zero_is_unknown" and _decimal_zero(text):
            # R10. A per-room price of 0 on a booking that was demonstrably paid for means the
            # tariff was never priced. This format says that with a null amount rather than by
            # overloading a number, so 0 stays available to mean nothing was charged.
            return {"amount": None, "currency": currency}
        return {"amount": text, "currency": currency}

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _stays_of(booking) -> list[SourceRecord]:
        """The room stays inside one booking, as source records that can read it upwards.

        Cut from the booking element rather than from the response, so a stay can only ever be
        paired with the booking that actually contains it (R7).
        """
        return [SourceRecord(booking.endpoint, element, entity="stay",
                             ancestors=(booking.element,))
                for element in find_elements(booking.element, "RoomStay")]


class _Absent:
    """Distinct from None, which this wire format uses for 'present and empty'."""

    def __repr__(self) -> str:
        return "ABSENT"


_ABSENT = _Absent()


def _set(node: dict, path: str, value: Any) -> None:
    """Write a value at a DemoPMS path, creating the objects on the way.

    Understands the `key[child=value]` form, because per-guest-type capacity is a list of
    objects distinguished by a key one of them carries, and that shape has to be built rather
    than assumed to exist.
    """
    segments = path.split(".")
    for segment in segments[:-1]:
        if "[" in segment:
            key, predicate = segment[:-1].split("[", 1)
            child, wanted = predicate.split("=", 1)
            bucket = node.setdefault(key, [])
            match = next((e for e in bucket if e.get(child) == wanted), None)
            if match is None:
                match = {child: wanted}
                bucket.append(match)
            node = match
        else:
            node = node.setdefault(segment, {})
    node[segments[-1]] = value


def _translate(table: dict[str, str], code: str, what: str) -> str:
    try:
        return table[code]
    except KeyError:
        raise Unencodable(
            "%r is a %s this tool has not been told how to translate. Adding a plausible "
            "spelling would give the demo hotel a fact the captured one does not have - decide "
            "what it becomes and put it in the table" % (code, what)) from None


def _int(canonical: str, text: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise Unencodable("%s carries %r, which is not a number" % (canonical, text)) from None


def _bool(canonical: str, text: str) -> bool:
    upper = text.upper()
    if upper in ("YES", "TRUE", "1"):
        return True
    if upper in ("NO", "FALSE", "0"):
        return False
    raise Unencodable("%s carries %r, which is neither true nor false" % (canonical, text))


def _decimal_zero(text: str) -> bool:
    from decimal import Decimal, InvalidOperation
    try:
        return Decimal(text) == 0
    except (InvalidOperation, ArithmeticError, ValueError):
        return False


# ---------------------------------------------------------------------------- the index
def build_index(source_index: dict[str, Any]) -> dict[str, Any]:
    """The demo fixture index: the same fingerprints, in the other request vocabulary.

    Translated rather than invented, so a window one provider refuses is refused by the other
    (F19c, issue #9) and the two stay comparable in what they can and cannot answer. A demo
    hotel that could answer questions the captured one cannot would make criterion 7 pass by
    being a different hotel.
    """
    captures = {}
    for name, meta in source_index["captures"].items():
        captures[CAPTURES[name]] = {
            "label": meta["label"],
            "as_of": meta["as_of"],
            "transcoded_from": "the %s MiniHotel capture, %s" % (name, meta["captured_at"]),
        }

    responses = []
    for entry in source_index["responses"]:
        if entry["file"] not in FILES or not entry.get("captures"):
            continue
        responses.append({
            "file": FILES[entry["file"]],
            "endpoint": ENDPOINTS[entry["endpoint"]],
            "request": _translate_request(entry["request"]),
            "captures": [CAPTURES[c] for c in entry["captures"]],
            "transcoded_from": entry["file"],
            "note": entry.get("note", ""),
        })

    return {
        "provider": "demopms",
        "source": "transcoded from fixtures/minihotel/ by tools/transcode_demopms.py",
        "note": (
            "FICTIONAL BY CONSTRUCTION, AND THE SAME HOTEL. Every record here is a re-encoding "
            "of a real captured MiniHotel response - the same reservations, rooms, folios and "
            "occupancy segments, in a wire format with deliberately different quirks. Nothing "
            "was invented and nothing was filled in: the folios that were never captured are "
            "still missing, the statuses nobody can name are still unnameable, and the rooms "
            "with no configured capacity are still unconfigured. `is_synthetic` is True on "
            "every run over this evidence, because a run over records this repository produced "
            "must say so."),
        "rebuild": "python3 -m tools.transcode_demopms --check",
        "captures": captures,
        "responses": responses,
    }


def _translate_request(request: dict[str, Any]) -> dict[str, Any]:
    translated: dict[str, Any] = {}
    for name, value in request.items():
        if name == "BookingSearch":
            # A nested search object on one provider is a flat parameter on the other, which is
            # the sort of difference that has to be absorbed here rather than in an IR.
            translated["state"] = STATUS[value["Status"]]
            continue
        key = FILTERS[name]
        if isinstance(value, dict):
            translated[key] = {"from": value.get("From", value.get("from")),
                               "to": value.get("To", value.get("to"))}
        elif isinstance(value, str) and value.lower() in ("true", "false"):
            translated[key] = value.lower() == "true"
        else:
            translated[key] = value
    return translated


# ---------------------------------------------------------------------------- entry point
def build() -> dict[str, str]:
    """Every demo fixture, as filename -> exact file content."""
    transcoder = Transcoder()
    built = {}
    for entry in transcoder.source_index["responses"]:
        if entry["file"] not in FILES or not entry.get("captures"):
            continue
        built[FILES[entry["file"]]] = _dump(transcoder.document(entry))
    built["index.json"] = _dump(build_index(transcoder.source_index))
    return built


def _dump(document: Any) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    built = build()
    check = "--check" in argv
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    differences = []
    for name, content in sorted(built.items()):
        path = TARGET_DIR / name
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == content:
            continue
        differences.append(name)
        if not check:
            path.write_text(content, encoding="utf-8")

    stale = sorted(p.name for p in TARGET_DIR.glob("*.json") if p.name not in built)
    for name in stale:
        differences.append("%s (no longer produced)" % name)
        if not check:
            (TARGET_DIR / name).unlink()

    if check and differences:
        print("STALE - %d file(s) differ from a rebuild:" % len(differences))
        for name in differences:
            print("   x %s" % name)
        return 1

    print("%s %d file(s) in %s" % ("checked" if check else "wrote", len(built),
                                   TARGET_DIR.relative_to(ROOT)))
    if differences and not check:
        for name in differences:
            print("   ~ %s" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
