# -*- coding: utf-8 -*-
"""
RUN STORE - history, in SQLite.

A verdict that cannot be re-read is not an audit trail. The store exists so a result can be
looked at again WITHOUT re-querying the PMS - which matters more here than it sounds, because a
folio costs one call per reservation (R1) and re-running to answer "what did it say?" is the
expensive mistake this prevents.

`sqlite3` is in the standard library, so the zero-dependency rule holds and there is still no
install step. v1 wrote one JSON file per run and indexed none of them, so there was no history,
no trend, and no way to ask "has this control been failing all week" - which is what
"continuous assurance" in the PRD means (review finding F14).

THE THING THAT MUST NOT BE LOST
-------------------------------
The evidence table, exactly as it was: value, unit, whether it was known, the reason it was not,
the risk id, and the provenance. A stored FAIL with the number missing is an accusation without
a receipt.

The `not_applicable` sentinel gets its own encoding rather than being written as null or "".
R7 is the reason: "there is no channel confirmation because this was a direct booking" must
survive as that, or every direct booking looks like a duplicate of every other one again.

So does the run's FRESHNESS (finding F7): when the evidence was obtained, and what the control
asked for. Re-reading a stored run has to report what was true when it ran, not what would be
true if it ran now - a verdict's freshness is a property of the run rather than of the reader.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sqlite3
from datetime import datetime
from decimal import Decimal

from ..kernel import NOT_APPLICABLE, EvidenceLine, Money, Outcome, Value, Verdict
from ..runner import Run

SCHEMA = pathlib.Path(__file__).resolve().parent / "schema.sql"

_NOT_APPLICABLE_TAG = {"__not_applicable__": True}


# --------------------------------------------------------------------------- encoding
def encode_payload(payload) -> str | None:
    """A value's payload as JSON, with the types the kernel cares about tagged.

    Money and the not-applicable sentinel are tagged rather than flattened: an amount that came
    back as a bare number would have lost its currency (R9), and a sentinel written as null
    would be indistinguishable from an evidence gap (R7).
    """
    if payload is NOT_APPLICABLE:
        return json.dumps(_NOT_APPLICABLE_TAG)
    if isinstance(payload, Money):
        return json.dumps({"__money__": str(payload.amount), "currency": payload.currency})
    if isinstance(payload, Decimal):
        return json.dumps({"__decimal__": str(payload)})
    if isinstance(payload, tuple):
        return json.dumps({"__tuple__": list(payload)})
    return json.dumps(payload)


def decode_payload(text: str | None):
    if text is None:
        return None
    value = json.loads(text)
    if isinstance(value, dict):
        if value.get("__not_applicable__"):
            return NOT_APPLICABLE
        if "__money__" in value:
            return Money(Decimal(value["__money__"]), value["currency"])
        if "__decimal__" in value:
            return Decimal(value["__decimal__"])
        if "__tuple__" in value:
            return tuple(value["__tuple__"])
    return value


def make_run_id(run: Run) -> str:
    """A stable identity for one run: which control, over what, as of when, made when."""
    seed = "|".join((run.control_id, run.tenant_id, run.provider, run.evidence_label,
                     run.as_of, run.created_at.isoformat()))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- store
class RunStore:
    """Runs on disk, queryable. Opened lazily and migrated from empty on first use."""

    def __init__(self, path: pathlib.Path | str = ":memory:") -> None:
        self.path = str(path)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        # No manual setup step: an empty file becomes a valid database on the first open.
        self._connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        self._migrate()
        self._connection.commit()

    def _migrate(self) -> None:
        """Bring an older database up to the current schema.

        `CREATE TABLE IF NOT EXISTS` builds a new file correctly and does nothing at all to one
        that already exists, so a column added later would be missing from every database made
        before it - and the failure would arrive as an operational error in the middle of
        saving a run. Columns are added here instead, nullable, so an old run reads back as a
        run that cannot say when its evidence was obtained. Which is true, and which the
        freshness verdict reports as stale rather than assuming.
        """
        existing = {row["name"] for row in
                    self._connection.execute("PRAGMA table_info(runs)")}
        for column in ("observed_at", "maximum_age"):
            if column not in existing:
                self._connection.execute("ALTER TABLE runs ADD COLUMN %s TEXT" % column)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "RunStore":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ------------------------------------------------------------------ writing
    def save(self, run: Run) -> str:
        run_id = run.run_id or make_run_id(run)
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, run.control_id, run.control_name, run.natural_language, run.tenant_id,
                 run.provider, run.evidence_label, int(run.evidence_is_synthetic), run.as_of,
                 run.created_at.isoformat(), run.calls, run.blocked,
                 run.observed_at.isoformat() if run.observed_at else None,
                 run.maximum_age or None))
            self._connection.execute("DELETE FROM verdicts WHERE run_id = ?", (run_id,))
            self._connection.execute("DELETE FROM evidence WHERE run_id = ?", (run_id,))
            for position, verdict in enumerate(run.verdicts):
                self._connection.execute(
                    "INSERT INTO verdicts VALUES (?,?,?,?,?)",
                    (run_id, position, verdict.outcome.value, verdict.reason,
                     verdict.record_id))
                for line_number, line in enumerate(verdict.evidence):
                    value = line.value
                    self._connection.execute(
                        "INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (run_id, position, line_number, line.field, int(value.is_known),
                         encode_payload(value.payload) if value.is_known else None,
                         value.unit, value.reason, value.risk, line.source))
        return run_id

    # ------------------------------------------------------------------ reading
    def load(self, run_id: str) -> Run | None:
        """Re-read a stored run WITHOUT spending a single provider call (R1)."""
        row = self._connection.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None

        evidence: dict[int, list[EvidenceLine]] = {}
        for line in self._connection.execute(
                "SELECT * FROM evidence WHERE run_id = ? ORDER BY position, line", (run_id,)):
            value = (Value.known(decode_payload(line["payload_json"]), unit=line["unit"],
                                 source=line["source"])
                     if line["is_known"]
                     else Value.unknown(line["reason"], risk=line["risk"],
                                        source=line["source"]))
            evidence.setdefault(line["position"], []).append(
                EvidenceLine(line["field"], value, source=line["source"]))

        verdicts = tuple(
            Verdict(Outcome(v["outcome"]), v["reason"], evidence.get(v["position"], []),
                    control_id=row["control_id"], record_id=v["record_id"])
            for v in self._connection.execute(
                "SELECT * FROM verdicts WHERE run_id = ? ORDER BY position", (run_id,)))

        return Run(
            control_id=row["control_id"], control_name=row["control_name"],
            natural_language=row["natural_language"], tenant_id=row["tenant_id"],
            provider=row["provider"], evidence_label=row["evidence_label"],
            evidence_is_synthetic=bool(row["evidence_is_synthetic"]), as_of=row["as_of"],
            created_at=datetime.fromisoformat(row["created_at"]), calls=row["calls"],
            verdicts=verdicts, blocked=row["blocked"], run_id=run_id,
            observed_at=(datetime.fromisoformat(row["observed_at"])
                         if row["observed_at"] else None),
            maximum_age=row["maximum_age"] or "")

    def history(self, control_id: str | None = None, limit: int = 50) -> list[dict]:
        """Past runs, newest first, as summaries.

        Summaries rather than whole runs: a history page wants counts and a date, and loading
        every evidence table to render a list would make the cheap thing expensive.
        """
        query = ("SELECT r.run_id, r.control_id, r.as_of, r.created_at, r.calls, r.blocked, "
                 "  SUM(v.outcome = 'PASS') AS passes, SUM(v.outcome = 'FAIL') AS fails, "
                 "  SUM(v.outcome = 'UNKNOWN') AS unknowns, "
                 "  SUM(v.outcome = 'EXCLUDED') AS excluded, COUNT(v.position) AS total "
                 "FROM runs r LEFT JOIN verdicts v ON v.run_id = r.run_id ")
        params: tuple = ()
        if control_id is not None:
            query += "WHERE r.control_id = ? "
            params = (control_id,)
        query += "GROUP BY r.run_id ORDER BY r.created_at DESC LIMIT ?"

        return [dict(row) for row in
                self._connection.execute(query, params + (limit,))]
