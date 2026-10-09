/**
 * The ONLY module in this UI that calls the engine. Server-side only.
 *
 * WHY ONE MODULE: `GET /api/run/` is not a read. It spends provider calls - for a folio, one per
 * reservation, with no bulk endpoint behind it (R1) - and writes a row to the run store (trap 4).
 * Everything else here is free. Keeping every request in one file means the expensive one is
 * findable, and a test over the tree (tests/unit/test_ui_hygiene.py) refuses `fetch(` anywhere
 * else, so a component cannot quietly start running controls from a render or an effect.
 *
 * The browser never talks to the engine: these run in Server Components and one Server Action,
 * so there is no CORS to configure and the engine's Content-Security-Policy is untouched.
 */
import type { ControlEntry, Outcomes, Properties, ReadinessReport, RunPayload } from "./types";

/** Where the engine listens. Not a secret, so it has a default: the engine's own default port. */
const ENGINE = process.env.HOTELCONTROLS_API_URL ?? "http://127.0.0.1:8765";

/** A refusal from the engine, with the status and the sentence it gave. */
export class EngineRefused extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function read<T>(path: string): Promise<T> {
  // `no-store`: every answer here is either free and must be current, or (a run) must happen
  // exactly when asked and never be replayed from a cache as if it were new.
  const response = await fetch(ENGINE + path, { cache: "no-store" });
  const body = await response.json();
  if (!response.ok) {
    throw new EngineRefused(response.status, String(body?.error ?? response.statusText));
  }
  return body as T;
}

const id = encodeURIComponent;

// ---------------------------------------------------------------- free: no provider call
export const getControls = () => read<{ controls: ControlEntry[] }>("/api/controls");
export const getProperties = () => read<Properties>("/api/properties");
export const getOutcomes = () => read<Outcomes>("/api/outcomes");
/** Composed drafts, each flagged unreviewed. `wired: false` when the engine files none. */
export const getDrafts = () => read<{ wired: boolean; drafts: ControlEntry[] }>("/api/drafts");
export const getReadiness = (controlId: string) =>
  read<{ control_id: string; providers: ReadinessReport[] }>(`/api/readiness/${id(controlId)}`);
/** A past run, re-read from the store. Zero provider calls by construction (R1). */
export const getStoredRun = (runId: string) => read<RunPayload>(`/api/runs/${id(runId)}`);

// ---------------------------------------------------------------- COSTS PROVIDER CALLS
/**
 * Run a control over one body of evidence. Spends provider calls and writes the store.
 *
 * Called from exactly one place: the Server Action behind the "Run" button, which is a POST and
 * so is never prefetched, never double-fired by StrictMode and never refetched on focus. The
 * result is then read back from `/runs/<run_id>`, which is free and safe to reload.
 */
export const runControlOnce = (controlId: string, property: string, evidence: string) =>
  read<RunPayload>(
    `/api/run/${id(controlId)}?property=${id(property)}&evidence=${id(evidence)}`,
  );
