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
    maximum_age           TEXT,
    -- Slice 16 (G6b): which version of the rule judged this run, and the SHA-256 of that rule's
    -- verdict-bearing content. Both nullable for the same reason as the two above: a run stored
    -- before rules were versioned cannot say, and it reads back as "version not recorded"
    -- rather than borrowing today's version.
    policy_version        INTEGER,
    policy_digest         TEXT
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

-- Slice 18 (G2(a), G8's queue, G10c): the findings queue. One row per task a FAIL raised.
--
-- THE NATURAL KEY IS THE IDEMPOTENCY. (property, control, policy version, record): a control
-- run five times raises one task, and the same record failing under a NEW version of the rule
-- is a new task while the old one stays linked to the version that raised it. `make_run_id` is
-- untouched (plan-v3 §6.6) - runs repeat honestly; what must not repeat is the task.
--
-- TENANT-OWNED, so every read, update and delete on it carries `tenant_id = ?` after its WHERE.
-- `tests/unit/test_tenant_scoped_store.py` discovers this table from this file and enforces
-- that over every literal in store/ and every statement SQLite executes.
--
-- ADVISORY. `state` is changed by a person and by nothing else. A later run writes only the
-- receipt columns: the newest run that still found it failing, or a PASS since then. Neither
-- is a state; a PASS annotates a task and never closes it (D12).
CREATE TABLE IF NOT EXISTS actions (
    action_id        TEXT PRIMARY KEY,      -- a digest of the natural key, stable across processes
    tenant_id        TEXT NOT NULL,
    control_id       TEXT NOT NULL,
    control_name     TEXT NOT NULL,
    policy_version   INTEGER NOT NULL,      -- never null: a run that cannot name its rule raises nothing
    policy_digest    TEXT NOT NULL,
    record_id        TEXT NOT NULL,
    -- From the IR's own `action` block, copied when the task is raised. `audience` is optional
    -- in the IR schema, and a rule that names none gets a task for no audience, not a default.
    severity         TEXT NOT NULL,
    audience         TEXT,
    kind             TEXT NOT NULL,
    -- The FAIL verdict's own sentence: the amount travels WITH its currency (R9). The full
    -- evidence trail is the stored run `raised_by_run` names, never a second copy here.
    reason           TEXT NOT NULL,
    raised_by_run    TEXT NOT NULL,
    raised_at        TEXT NOT NULL,
    as_of            TEXT NOT NULL,
    provider         TEXT NOT NULL,
    evidence_label   TEXT NOT NULL,
    state            TEXT NOT NULL DEFAULT 'pending'
                     CHECK (state IN ('pending', 'done', 'dismissed')),
    state_changed_at TEXT,
    state_changed_by TEXT,
    last_failing_run TEXT NOT NULL,
    last_failing_at  TEXT NOT NULL,
    cleared_by_run   TEXT,
    cleared_at       TEXT,
    cleared_as_of    TEXT,
    -- Slice 19: the sent marker. CLAIMED before a send by a guarded UPDATE, released with the
    -- reason if the send fails, so a task is emailed once per channel however often dispatch
    -- runs. `notify_note` says why a task is unsent ("no route configured for audience
    -- finance"). A store made by slice 18 gains these through `_migrate`, nullable: never sent.
    notified_at      TEXT,
    notified_via     TEXT,
    notify_note      TEXT,
    UNIQUE (tenant_id, control_id, policy_version, record_id)
);

CREATE INDEX IF NOT EXISTS actions_by_tenant ON actions(tenant_id, state);
