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
 * and one route handler (the stylesheet), so there is no CORS to configure and the engine's
 * Content-Security-Policy is untouched. Every one reads the engine's address at RUN time.
 */
import type {
  AcceptRefused,
  ComposeState,
  ComposeTurnResponse,
  ControlEntry,
  History,
  Outcomes,
  Properties,
  ReadinessReport,
  RunPayload,
} from "./types";

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

/** A form POST to one of the engine's compose routes. Fields are an explicit allow-list. */
async function send(path: string, fields: Record<string, string>): Promise<{ status: number; body: unknown }> {
  const response = await fetch(ENGINE + path, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(fields).toString(),
    cache: "no-store",
  });
  return { status: response.status, body: await response.json() };
}

function refuse(status: number, body: unknown): never {
  throw new EngineRefused(status, String((body as { error?: string })?.error ?? status));
}

const id = encodeURIComponent;

// ---------------------------------------------------------------- free: no provider call
/** The engine's own stylesheet, so both surfaces share one set of criterion-2 rules. */
export async function getStylesheet(): Promise<string> {
  const response = await fetch(ENGINE + "/style.css", { cache: "no-store" });
  if (!response.ok) throw new EngineRefused(response.status, "the engine did not serve its stylesheet");
  return response.text();
}
export const getControls = () => read<{ controls: ControlEntry[] }>("/api/controls");
export const getProperties = () => read<Properties>("/api/properties");
export const getOutcomes = () => read<Outcomes>("/api/outcomes");
/**
 * Since slice 17 the engine reads drafts, history and stored runs FOR a property, so each of
 * these names one. Another property's run is a 404, exactly like a run that never existed.
 */
/** One property's composed drafts, each flagged unreviewed. `wired: false` when none are filed. */
export const getDrafts = (property: string) =>
  read<{ wired: boolean; drafts: ControlEntry[] }>(`/api/drafts?property=${id(property)}`);
export const getReadiness = (controlId: string, property: string) =>
  read<{ control_id: string; providers: ReadinessReport[] }>(
    `/api/readiness/${id(controlId)}?property=${id(property)}`,
  );
/** One property's past runs of a control, newest first. Read from the store; no provider call. */
export const getHistory = (controlId: string, property: string) =>
  read<History>(`/api/history/${id(controlId)}?property=${id(property)}`);
/** When a control runs next on a property's provider, as of an instant (F7). From the spec alone. */
export const getPlan = (controlId: string, property: string, asOf: string) =>
  read<{ control_id: string; property: string; as_of: string; mode: string; declared_mode: string; fell_back: boolean; headline: string }>(
    `/api/plan/${id(controlId)}?property=${id(property)}&as_of=${id(asOf)}`,
  );
/** A past run, re-read from the store for its property. Zero provider calls by construction (R1). */
export const getStoredRun = (runId: string, property: string) =>
  read<RunPayload>(`/api/runs/${id(runId)}?property=${id(property)}`);

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

// ---------------------------------------------------------------- compose: writes OUR drafts only
/** Whether compose is wired, and one conversation's transcript. Free. */
export const getComposeState = () => read<ComposeState>("/api/compose");

/** One exchange with the proposer. Writes nothing but the engine's in-memory transcript. */
export async function composeTurn(fields: { prose: string; conversation: string; template: string }) {
  const { status, body } = await send("/api/compose", fields);
  if (status !== 200) refuse(status, body);
  return body as ComposeTurnResponse;
}

/**
 * File the sentence sent back as an unreviewed draft in the engine's drafts directory. Never a
 * PMS. 201 when filed; 422 - with the validator's reasons - when the grammar refuses it.
 */
export async function composeAccept(fields: Record<string, string>) {
  const { status, body } = await send("/api/compose/accept", fields);
  if (status === 201) {
    return { status, body: body as { control_id: string; property: string; evidence: string; reviewed: false } } as const;
  }
  if (status === 422) return { status, body: body as AcceptRefused } as const;
  return refuse(status, body);
}
