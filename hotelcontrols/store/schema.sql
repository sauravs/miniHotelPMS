-- Run history. SQLite because it is in the standard library, so the zero-dependency rule holds
-- and there is still no install step.
--
-- THE THING THAT MUST NOT BE LOST is the evidence table, exactly as it was: the value, its
-- unit, whether it was known, the reason it was not, the risk id, and where it came from. A
-- stored FAIL with the number missing is an accusation without a receipt, and an UNKNOWN
-- without its reason cannot tell a hotel what to fix.

CREATE TABLE IF NOT EXISTS runs (
    run_id                TEXT PRIMARY KEY,
    control_id            TEXT NOT NULL,
    control_name          TEXT NOT NULL,
    natural_language      TEXT NOT NULL,
    tenant_id             TEXT NOT NULL,
    provider              TEXT NOT NULL,
    evidence_label        TEXT NOT NULL,
    evidence_is_synthetic INTEGER NOT NULL,
    as_of                 TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    calls                 INTEGER NOT NULL,
    blocked               TEXT,
    -- Finding F7's freshness half. `observed_at` is when the evidence was OBTAINED, which is a
    -- different fact from `as_of` (what date it describes) and from `created_at` (when the run
    -- happened). `maximum_age` is what the control asked for, carried on the run so a stored
    -- verdict can still answer "was this current?" without re-reading the IR it came from.
    -- Both nullable: a run made before this column existed cannot say, and a run that cannot
    -- say is reported as stale rather than assumed fresh.
    observed_at           TEXT,
    maximum_age           TEXT
);

CREATE TABLE IF NOT EXISTS verdicts (
    run_id     TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    position   INTEGER NOT NULL,
    outcome    TEXT NOT NULL,
    reason     TEXT NOT NULL,
    record_id  TEXT,
    PRIMARY KEY (run_id, position)
);

CREATE TABLE IF NOT EXISTS evidence (
    run_id         TEXT NOT NULL,
    position       INTEGER NOT NULL,
    line           INTEGER NOT NULL,
    field          TEXT NOT NULL,
    is_known       INTEGER NOT NULL,
    -- Payloads are stored as JSON so a Decimal amount, a tuple of room-type codes and the
    -- not-applicable sentinel all survive a round trip without a second encoding to remember.
    payload_json   TEXT,
    unit           TEXT,
    reason         TEXT,
    risk           TEXT,
    source         TEXT,
    PRIMARY KEY (run_id, position, line),
    FOREIGN KEY (run_id, position) REFERENCES verdicts(run_id, position) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS runs_by_control ON runs(control_id, created_at DESC);
