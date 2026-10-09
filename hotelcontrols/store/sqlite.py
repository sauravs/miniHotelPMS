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

EVERY READ NAMES ITS PROPERTY (slice 17, G5)
--------------------------------------------
One store holds every property's runs, and one missed `WHERE` would hand one hotel another's
verdicts - a breach, not a bug. So every read takes the property as a KEYWORD-ONLY argument with
NO DEFAULT: a call without one is a `TypeError` where it is written, never a query that quietly
returns everything. Another property's run reads as absent, exactly like a run that never
existed, so a run id cannot be probed for existence. And every SQL statement here that reads,
updates or deletes a tenant-owned table carries a bound tenant predicate in its own text - which
`tests/unit/test_tenant_scoped_store.py` checks over every literal in this package and over every
statement SQLite actually executes, for every table `schema.sql` creates, including the ones v3
adds later. `verdicts` and `evidence` carry no property of their own; they are scoped through
their run, by a join or a subquery on `runs.tenant_id`.
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

# The `runs` columns a save writes, in one place, so the insert and its update half cannot list
# different ones. `run_id` first: it is the conflict key and is never updated.
_RUN_COLUMNS = ("run_id", "control_id", "control_name", "natural_language", "tenant_id",
                "provider", "evidence_label", "evidence_is_synthetic", "as_of", "created_at",
                "calls", "blocked", "observed_at", "maximum_age", "policy_version",
                "policy_digest")


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
        # Slice 16 adds the policy pair the same way. A run stored before it reads back with
        # neither, which the surfaces show as "version not recorded" - never as today's version.
        for column, kind in (("observed_at", "TEXT"), ("maximum_age", "TEXT"),
                             ("policy_version", "INTEGER"), ("policy_digest", "TEXT")):
            if column not in existing:
                self._connection.execute("ALTER TABLE runs ADD COLUMN %s %s" % (column, kind))

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
            # Columns NAMED rather than positional. A migrated database gains its columns in the
            # order they were added and a fresh one in the order the schema lists them; naming
            # them is what makes those two orders irrelevant.
            #
            # An UPSERT whose update half fires only for the SAME property (slice 17). The
            # `INSERT OR REPLACE` this used to be replaced by run id alone. Ids hash the
            # property, so two properties' runs do not collide by accident - but a run carrying
            # another property's id would have replaced that property's verdicts. Now it
            # changes no row, and is refused by name.
            written = self._connection.execute(
                "INSERT INTO runs (%s) VALUES (%s) ON CONFLICT(run_id) DO UPDATE SET %s "
                "WHERE runs.tenant_id = excluded.tenant_id"
                % (", ".join(_RUN_COLUMNS), ",".join("?" * len(_RUN_COLUMNS)),
                   ", ".join("%s = excluded.%s" % (c, c) for c in _RUN_COLUMNS[1:])),
                (run_id, run.control_id, run.control_name, run.natural_language, run.tenant_id,
                 run.provider, run.evidence_label, int(run.evidence_is_synthetic), run.as_of,
                 run.created_at.isoformat(), run.calls, run.blocked,
                 run.observed_at.isoformat() if run.observed_at else None,
                 run.maximum_age or None, run.policy_version, run.policy_digest))
            if written.rowcount != 1:
                raise ValueError("run id %r already belongs to another property; refusing to "
                                 "replace its verdicts" % run_id)
            # Scoped through the run, like every other statement on a tenant-owned table.
            self._connection.execute(
                "DELETE FROM verdicts WHERE run_id IN "
                "(SELECT run_id FROM runs WHERE run_id = ? AND tenant_id = ?)",
                (run_id, run.tenant_id))
            self._connection.execute(
                "DELETE FROM evidence WHERE run_id IN "
                "(SELECT run_id FROM runs WHERE run_id = ? AND tenant_id = ?)",
                (run_id, run.tenant_id))
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
    def load(self, run_id: str, *, tenant_id: str) -> Run | None:
        """Re-read a stored run WITHOUT spending a single provider call (R1).

        `tenant_id` is keyword-only with no default (slice 17): a run is read FOR a property.
        Another property's run returns None, exactly as a run that does not exist does, so the
        web layer answers both with the same 404 and a run id cannot be probed for existence.
        """
        row = self._connection.execute(
            "SELECT * FROM runs WHERE run_id = ? AND tenant_id = ?",
            (run_id, tenant_id)).fetchone()
        if row is None:
            return None

        evidence: dict[int, list[EvidenceLine]] = {}
        for line in self._connection.execute(
                "SELECT e.* FROM evidence e JOIN runs r ON r.run_id = e.run_id "
                "WHERE e.run_id = ? AND r.tenant_id = ? ORDER BY e.position, e.line",
                (run_id, tenant_id)):
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
                "SELECT v.* FROM verdicts v JOIN runs r ON r.run_id = v.run_id "
                "WHERE v.run_id = ? AND r.tenant_id = ? ORDER BY v.position",
                (run_id, tenant_id)))

        return Run(
            control_id=row["control_id"], control_name=row["control_name"],
            natural_language=row["natural_language"], tenant_id=row["tenant_id"],
            provider=row["provider"], evidence_label=row["evidence_label"],
            evidence_is_synthetic=bool(row["evidence_is_synthetic"]), as_of=row["as_of"],
            created_at=datetime.fromisoformat(row["created_at"]), calls=row["calls"],
            verdicts=verdicts, blocked=row["blocked"], run_id=run_id,
            observed_at=(datetime.fromisoformat(row["observed_at"])
                         if row["observed_at"] else None),
            maximum_age=row["maximum_age"] or "",
            policy_version=row["policy_version"], policy_digest=row["policy_digest"])

    def history(self, control_id: str | None = None, limit: int = 50, *,
                tenant_id: str) -> list[dict]:
        """One property's past runs, newest first, as summaries.

        `tenant_id` is keyword-only with no default (slice 17): there is no "every property's
        history", because nothing that reads it is entitled to it.

        Summaries rather than whole runs: a history page wants counts and a date, and loading
        every evidence table to render a list would make the cheap thing expensive.
        """
        # `evidence_label` and `provider` are in the summary because a history row without them
        # is not a history: two runs of one control over two different bodies of evidence are
        # two different questions, and a list that cannot tell them apart is a list of dates.
        # The policy pair is in the summary because history groups by it (slice 16): two runs
        # of one control under v2 and v3 of its rule answered two different rules.
        query = ("SELECT r.run_id, r.control_id, r.as_of, r.created_at, r.calls, r.blocked, "
                 "  r.evidence_label, r.provider, r.policy_version, r.policy_digest, "
                 "  SUM(v.outcome = 'PASS') AS passes, SUM(v.outcome = 'FAIL') AS fails, "
                 "  SUM(v.outcome = 'UNKNOWN') AS unknowns, "
                 "  SUM(v.outcome = 'EXCLUDED') AS excluded, COUNT(v.position) AS total "
                 "FROM runs r LEFT JOIN verdicts v ON v.run_id = r.run_id "
                 "WHERE r.tenant_id = ? ")
        params: tuple = (tenant_id,)
        if control_id is not None:
            query += "AND r.control_id = ? "
            params += (control_id,)
        # `run_id` breaks ties, and ties are the norm: both properties' 2026 captures describe
        # the same instant. SQLite promises no order among equal keys, so without it the order
        # of a history page was the SQLite build's (issue #35).
        query += "GROUP BY r.run_id ORDER BY r.created_at DESC, r.run_id DESC LIMIT ?"

        return [dict(row) for row in
                self._connection.execute(query, params + (limit,))]
