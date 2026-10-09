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

AND THE FINDINGS QUEUE LIVES HERE TOO (slice 18)
------------------------------------------------
The `actions` table: one task per FAIL, kept by its natural key - property, control, policy
version, record - so a control run five times raises one task (G10c, narrowed; `make_run_id`
is untouched). It is in this store, on this connection, because a task is only as good as the
stored run that is its receipt, and two databases could disagree about whether that run exists.
The same rule as every other table: every read names its property, keyword-only, no default.

AND EVERY GUEST DECISION (slice 22)
-----------------------------------
The `decisions` table: one row per decision, keyed by the approved table's identity digest, so
the same request twice is one row. A decision and the task it raises are written in ONE
transaction, the task through the same natural-key insert a FAIL's task uses - a crash between
the two cannot leave a decision whose task never existed. Reads name their property, keyword-
only, no default, and another property's decision is absent exactly like a missing one.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sqlite3
from datetime import date, datetime, time
from decimal import Decimal

from ..actions import (PENDING, STATES, ActionRecord, Finding, Findings, TransitionRefused,
                       check_transition)
from ..guest import Decision, Gap
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

# The `actions` columns a new task writes, in one place for the same reason. `state` is not
# here: it defaults to pending, and only `transition` - a person - ever writes it.
_ACTION_COLUMNS = ("action_id", "tenant_id", "control_id", "control_name", "policy_version",
                   "policy_digest", "record_id", "severity", "audience", "kind", "reason",
                   "raised_by_run", "raised_at", "as_of", "provider", "evidence_label",
                   "last_failing_run", "last_failing_at")

# The `decisions` columns, in one place, for the insert and for reading a row back (slice 22).
_DECISION_COLUMNS = ("decision_id", "tenant_id", "template_id", "template_name",
                     "template_version", "template_digest", "parameters_digest",
                     "reservation_id", "requested_time", "departure_date", "received_at",
                     "received_on", "decision", "rule", "reason", "fee_amount", "fee_currency",
                     "gaps_json", "evidence_json", "provider", "evidence_label", "severity",
                     "audience", "action_id")

# How a queue is read: what is still to do first, then the most urgent, then the newest.
_STATE_ORDER = {state: rank for rank, state in enumerate(STATES)}
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


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
        # Slice 19 adds the sent marker to slice 18's `actions` table the same way. A task
        # stored before it reads back as never sent - which is true.
        existing = {row["name"] for row in
                    self._connection.execute("PRAGMA table_info(actions)")}
        for column in ("notified_at", "notified_via", "notify_note"):
            if column not in existing:
                self._connection.execute("ALTER TABLE actions ADD COLUMN %s TEXT" % column)

    @property
    def persistent(self) -> bool:
        """Whether what is written here survives the process. The demo's default does not,
        and the queue page says so rather than implying a persistence it lacks (brief §8.8)."""
        return self.path not in (":memory:", "")

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

    # ------------------------------------------------------------------ the findings queue
    def record_findings(self, findings: Findings) -> int:
        """Keep what one run raised. Returns how many tasks are NEW - zero for a repeat.

        A FAIL whose natural key already has a task changes no state: it updates the receipt
        (the newest run still finding it failing) and removes a PASS annotation it outdates. A
        PASS annotates a task raised earlier under the same rule, and never closes it - a
        person does (D12). Nothing here reads a wall clock; every instant is the run's own.
        """
        for finding in findings.failing:
            if finding.tenant_id != findings.tenant_id:
                # A batch is one run's, for one property. A record inside it naming another
                # property would land in the wrong hotel's queue.
                raise ValueError("a finding for property %r arrived in a batch for property "
                                 "%r; refusing to write it into either queue"
                                 % (finding.tenant_id, findings.tenant_id))
        created = 0
        with self._connection:
            for finding in findings.failing:
                written = self._insert_action(finding)
                if written.rowcount == 1:
                    created += 1
                    continue
                row = self._action_by_key(findings, finding.record_id)
                # Compared as instants, not as strings: two ISO strings with different UTC
                # offsets (a daylight-saving change) do not sort in time order.
                if finding.raised_at >= datetime.fromisoformat(row["last_failing_at"]):
                    self._connection.execute(
                        "UPDATE actions SET last_failing_run = ?, last_failing_at = ? "
                        "WHERE action_id = ? AND tenant_id = ?",
                        (finding.run_id, finding.raised_at.isoformat(), row["action_id"],
                         findings.tenant_id))
                if row["cleared_at"] and \
                        finding.raised_at >= datetime.fromisoformat(row["cleared_at"]):
                    # Failing again since the PASS: "no longer failing" is no longer true.
                    self._connection.execute(
                        "UPDATE actions SET cleared_by_run = NULL, cleared_at = NULL, "
                        "cleared_as_of = NULL WHERE action_id = ? AND tenant_id = ?",
                        (row["action_id"], findings.tenant_id))
            for record_id in findings.passing:
                row = self._action_by_key(findings, record_id)
                # Strictly LATER than the newest failure. A tie is not later, and the
                # conservative reading of a tie is that it is still failing.
                if row is None or row["cleared_by_run"] is not None or \
                        findings.at <= datetime.fromisoformat(row["last_failing_at"]):
                    continue
                self._connection.execute(
                    "UPDATE actions SET cleared_by_run = ?, cleared_at = ?, cleared_as_of = ? "
                    "WHERE action_id = ? AND tenant_id = ?",
                    (findings.run_id, findings.at.isoformat(), findings.as_of,
                     row["action_id"], findings.tenant_id))
        return created

    def _insert_action(self, finding: Finding):
        """One task by its natural key, or nothing if that key already has one. The one insert
        into `actions`, shared by a FAIL's task (slice 18) and a guest decision's (slice 22)."""
        return self._connection.execute(
            "INSERT INTO actions (%s) VALUES (%s) ON CONFLICT(tenant_id, control_id, "
            "policy_version, record_id) DO NOTHING"
            % (", ".join(_ACTION_COLUMNS), ",".join("?" * len(_ACTION_COLUMNS))),
            (finding.action_id, finding.tenant_id, finding.control_id,
             finding.control_name, finding.policy_version, finding.policy_digest,
             finding.record_id, finding.severity, finding.audience, finding.kind,
             finding.reason, finding.run_id, finding.raised_at.isoformat(),
             finding.as_of, finding.provider, finding.evidence_label, finding.run_id,
             finding.raised_at.isoformat()))

    def _action_by_key(self, findings: Findings, record_id: str):
        """The task with this natural key in this batch's property, or None."""
        return self._connection.execute(
            "SELECT * FROM actions WHERE tenant_id = ? AND control_id = ? "
            "AND policy_version = ? AND record_id = ?",
            (findings.tenant_id, findings.control_id, findings.policy_version,
             record_id)).fetchone()

    def actions(self, *, tenant_id: str) -> list[ActionRecord]:
        """One property's queue: pending first, then the most urgent, then the newest.

        Sorted here rather than in SQL because `raised_at` is an ISO string with an offset,
        and strings with two different offsets do not sort in time order.
        """
        rows = self._connection.execute(
            "SELECT * FROM actions WHERE tenant_id = ?", (tenant_id,)).fetchall()
        records = [_action_record(row) for row in rows]
        return sorted(records, key=lambda r: (_STATE_ORDER[r.state],
                                              _SEVERITY_ORDER.get(r.severity, 3),
                                              -r.raised_at.timestamp(), r.action_id))

    def action(self, action_id: str, *, tenant_id: str) -> ActionRecord | None:
        """One task, for its property. Another property's task is None, exactly like a task
        that never existed, so an id cannot be probed for existence (slice 17's rule)."""
        row = self._connection.execute(
            "SELECT * FROM actions WHERE action_id = ? AND tenant_id = ?",
            (action_id, tenant_id)).fetchone()
        return _action_record(row) if row is not None else None

    def transition(self, action_id: str, state: str, *, tenant_id: str, at: datetime,
                   actor: str) -> ActionRecord | None:
        """A person moves a task: pending -> done | dismissed, stamped with when and by whom.

        `at` comes from the caller's injected clock - `kernel/clock.py` is the only module that
        may read a wall clock - and must carry its timezone, for the same reason a clock's
        instant must. Returns None for a task this property does not have; raises
        `TransitionRefused` for one that is already closed.
        """
        if state not in STATES:
            check_transition(PENDING, state)            # raises, naming the real states
        if at.tzinfo is None:
            raise ValueError("a transition's instant must carry its timezone; without one "
                             "'when was this marked done?' has no answer")
        if not (isinstance(actor, str) and actor.strip()):
            raise ValueError("a transition needs a named actor - who marked it - even if, "
                             "until slice 24, that name is only 'operator'")
        current = self.action(action_id, tenant_id=tenant_id)
        if current is None:
            return None
        check_transition(current.state, state)
        with self._connection:
            moved = self._connection.execute(
                "UPDATE actions SET state = ?, state_changed_at = ?, state_changed_by = ? "
                "WHERE action_id = ? AND tenant_id = ? AND state = 'pending'",
                (state, at.isoformat(), actor, action_id, tenant_id))
        if moved.rowcount != 1:                         # closed between the read and the write
            check_transition(self.action(action_id, tenant_id=tenant_id).state, state)
        return self.action(action_id, tenant_id=tenant_id)


    # ------------------------------------------------------------------ the sent marker
    # Slice 19. One email per task per channel: the marker is claimed before a send, so
    # exactly one caller ever owns it, and released with the reason if the send fails.
    def claim_notification(self, action_id: str, *, tenant_id: str, channel: str,
                           at: datetime) -> bool:
        """Mark a task as being sent. True for exactly one caller; False if it already was, or
        if this property has no such task."""
        with self._connection:
            claimed = self._connection.execute(
                "UPDATE actions SET notified_at = ?, notified_via = ?, notify_note = NULL "
                "WHERE action_id = ? AND tenant_id = ? AND notified_at IS NULL",
                (at.isoformat(), channel, action_id, tenant_id))
        return claimed.rowcount == 1

    def release_notification(self, action_id: str, *, tenant_id: str,
                             note: str | None) -> None:
        """Undo a claim whose send failed, saying why, so the next dispatch can try again."""
        with self._connection:
            self._connection.execute(
                "UPDATE actions SET notified_at = NULL, notified_via = NULL, notify_note = ? "
                "WHERE action_id = ? AND tenant_id = ?", (note, action_id, tenant_id))

    def note_notification(self, action_id: str, *, tenant_id: str, note: str) -> None:
        """Say why an unsent task is unsent - never on one that was sent."""
        with self._connection:
            self._connection.execute(
                "UPDATE actions SET notify_note = ? "
                "WHERE action_id = ? AND tenant_id = ? AND notified_at IS NULL",
                (note, action_id, tenant_id))

    # ------------------------------------------------------------------ guest decisions
    # Slice 22. One row per decision, and at most one task, written together.
    def save_decision(self, decision: Decision,
                      task: Finding | None) -> tuple[Decision, bool]:
        """Keep a decision and the task it raises. Returns the STORED decision and whether it
        is new: the same request again returns the first decision, unchanged, and raises no
        second task (D1 §65) - the double tap is answered with what was already decided.
        """
        if task is not None and (task.tenant_id != decision.tenant_id
                                 or task.record_id != decision.decision_id):
            # A task in another property's name, or for another decision, would land in the
            # wrong queue or detach from its receipt. Refused before anything is written.
            raise ValueError("decision %s for property %r was handed a task for property %r "
                             "and record %r; refusing to write either"
                             % (decision.decision_id, decision.tenant_id, task.tenant_id,
                                task.record_id))
        with self._connection:
            written = self._connection.execute(
                "INSERT INTO decisions (%s) VALUES (%s) ON CONFLICT(decision_id) DO NOTHING"
                % (", ".join(_DECISION_COLUMNS), ",".join("?" * len(_DECISION_COLUMNS))),
                _decision_row(decision))
            if written.rowcount != 1:
                existing = self.decision(decision.decision_id, tenant_id=decision.tenant_id)
                if existing is None:
                    # The id hashes the property, so this is not an accident - and it is
                    # refused rather than answered with another hotel's decision.
                    raise ValueError("decision id %r already belongs to another property"
                                     % decision.decision_id)
                return existing, False
            if task is not None:
                self._insert_action(task)
        return decision, True

    def decision(self, decision_id: str, *, tenant_id: str) -> Decision | None:
        """One decision, for its property. Another property's is None, like a missing one."""
        row = self._connection.execute(
            "SELECT * FROM decisions WHERE decision_id = ? AND tenant_id = ?",
            (decision_id, tenant_id)).fetchone()
        return _decision(row) if row is not None else None

    def decisions(self, *, tenant_id: str, limit: int = 200) -> list[Decision]:
        """One property's decisions, most recently recorded first.

        By insertion order rather than `received_at`: in the demo every request is asked as
        of the capture's own instant, so the instants tie, and the order a person made them in
        is the order they expect to read them back in.
        """
        rows = self._connection.execute(
            "SELECT * FROM decisions WHERE tenant_id = ? ORDER BY rowid DESC LIMIT ?",
            (tenant_id, limit)).fetchall()
        return [_decision(row) for row in rows]


def _decision_row(decision: Decision) -> tuple:
    evidence = [{"field": line.field, "is_known": line.value.is_known,
                 "payload": (encode_payload(line.value.payload) if line.value.is_known
                             else None),
                 "unit": line.value.unit, "reason": line.value.reason, "risk": line.value.risk,
                 "source": line.source} for line in decision.evidence]
    gaps = [{"name": gap.name, "kind": gap.kind, "reason": gap.reason} for gap in decision.gaps]
    fee = decision.fee
    return (decision.decision_id, decision.tenant_id, decision.template_id,
            decision.template_name, decision.template_version, decision.template_digest,
            decision.parameters_digest, decision.reservation_id,
            decision.requested_time.strftime("%H:%M"), decision.departure_date,
            decision.received_at.isoformat(), decision.received_on.isoformat(),
            decision.decision, decision.rule, decision.reason,
            str(fee.amount) if fee is not None else None,
            fee.currency if fee is not None else None,
            json.dumps(gaps), json.dumps(evidence), decision.provider, decision.evidence_label,
            decision.severity, decision.audience, decision.action_id)


def _decision(row) -> Decision:
    lines = []
    for item in json.loads(row["evidence_json"]):
        value = (Value.known(decode_payload(item["payload"]), unit=item["unit"],
                             source=item["source"])
                 if item["is_known"]
                 else Value.unknown(item["reason"], risk=item["risk"], source=item["source"]))
        lines.append(EvidenceLine(item["field"], value, source=item["source"]))
    hour, minute = map(int, row["requested_time"].split(":"))
    return Decision(
        decision_id=row["decision_id"], tenant_id=row["tenant_id"],
        template_id=row["template_id"], template_name=row["template_name"],
        template_version=row["template_version"], template_digest=row["template_digest"],
        parameters_digest=row["parameters_digest"], reservation_id=row["reservation_id"],
        requested_time=time(hour, minute), departure_date=row["departure_date"],
        received_at=datetime.fromisoformat(row["received_at"]),
        received_on=date.fromisoformat(row["received_on"]), decision=row["decision"],
        rule=row["rule"], reason=row["reason"],
        fee=(Money(Decimal(row["fee_amount"]), row["fee_currency"])
             if row["fee_amount"] is not None else None),
        gaps=tuple(Gap(g["name"], g["kind"], g["reason"])
                   for g in json.loads(row["gaps_json"])),
        evidence=tuple(lines), provider=row["provider"], evidence_label=row["evidence_label"],
        severity=row["severity"], audience=row["audience"], action_id=row["action_id"])


def _action_record(row) -> ActionRecord:
    def instant(text):
        return datetime.fromisoformat(text) if text else None

    return ActionRecord(
        action_id=row["action_id"], tenant_id=row["tenant_id"], control_id=row["control_id"],
        control_name=row["control_name"], policy_version=row["policy_version"],
        policy_digest=row["policy_digest"], record_id=row["record_id"],
        severity=row["severity"], audience=row["audience"], kind=row["kind"],
        reason=row["reason"], raised_by_run=row["raised_by_run"],
        raised_at=instant(row["raised_at"]), as_of=row["as_of"], provider=row["provider"],
        evidence_label=row["evidence_label"], state=row["state"],
        state_changed_at=instant(row["state_changed_at"]),
        state_changed_by=row["state_changed_by"], last_failing_run=row["last_failing_run"],
        last_failing_at=instant(row["last_failing_at"]), cleared_by_run=row["cleared_by_run"],
        cleared_at=instant(row["cleared_at"]), cleared_as_of=row["cleared_as_of"],
        notified_at=instant(row["notified_at"]), notified_via=row["notified_via"],
        notify_note=row["notify_note"])
