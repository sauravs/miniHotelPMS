/**
 * A stored run, re-read from the engine's store. Zero provider calls by construction (R1), so
 * this page is safe to reload, bookmark, share and prefetch - which is why a run is always shown
 * HERE, never on the page that triggered it.
 *
 * A stored run carries no readiness (that is a fact about the spec, not about the run), so it
 * is fetched beside it - also free.
 */
import { notFound } from "next/navigation";
import { RunView } from "@/components/RunView";
import { EngineRefused, getOutcomes, getReadiness, getStoredRun } from "@/lib/api";

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
  const [outcomes, readiness] = await Promise.all([getOutcomes(), getReadiness(run.control_id)]);
  return <RunView run={run} outcomes={outcomes} readiness={readiness.providers} />;
}
