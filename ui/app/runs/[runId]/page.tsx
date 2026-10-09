/**
 * A stored run, re-read from the engine's store. Zero provider calls by construction (R1), so
 * this page is safe to reload, bookmark, share and prefetch - which is why a run is always shown
 * HERE, never on the page that triggered it.
 *
 * A stored run carries no readiness and no plan - both are facts about the spec, not about the
 * run - so they are fetched beside it, also free. The plan is asked for at the run's own instant,
 * so it says exactly what the live run said (asserted for every control in the engine's suite).
 */
import { notFound } from "next/navigation";
import { RunView } from "@/components/RunView";
import { EngineRefused, getOutcomes, getPlan, getReadiness, getStoredRun } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function StoredRunPage({
  params,
  searchParams,
}: {
  params: Promise<{ runId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ runId }, query] = await Promise.all([params, searchParams]);
  // Read FOR a property (slice 17): another property's run is the same 404 as one that never
  // existed, so this page cannot be used to learn which run ids exist elsewhere.
  const property = [query.property].flat()[0] ?? "";
  let run;
  try {
    run = await getStoredRun(runId, property);
  } catch (error) {
    if (error instanceof EngineRefused && error.status === 404) notFound();
    throw error;
  }
  const [outcomes, readiness, plan] = await Promise.all([
    getOutcomes(),
    getReadiness(run.control_id, run.tenant_id),
    getPlan(run.control_id, run.tenant_id, run.as_of),
  ]);
  return <RunView run={run} outcomes={outcomes} readiness={readiness.providers} plan={plan} />;
}
