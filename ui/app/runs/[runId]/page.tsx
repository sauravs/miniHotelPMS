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

export default async function StoredRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  let run;
  try {
    run = await getStoredRun(runId);
  } catch (error) {
    if (error instanceof EngineRefused && error.status === 404) notFound();
    throw error;
  }
  const [outcomes, readiness, plan] = await Promise.all([
    getOutcomes(),
    getReadiness(run.control_id),
    getPlan(run.control_id, run.tenant_id, run.as_of),
  ]);
  return <RunView run={run} outcomes={outcomes} readiness={readiness.providers} plan={plan} />;
}
