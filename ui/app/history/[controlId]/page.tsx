/**
 * One control's past runs, re-read from the engine's store. Every request here is free: the
 * history, the spec and the wording. Nothing on this page runs anything.
 */
import { notFound } from "next/navigation";
import { HistoryView } from "@/components/HistoryView";
import { EngineRefused, getControls, getDrafts, getHistory, getOutcomes } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HistoryPage({ params }: { params: Promise<{ controlId: string }> }) {
  const { controlId } = await params;
  let history;
  try {
    history = await getHistory(controlId);
  } catch (error) {
    // The engine refuses an id it does not know with the same 404 its own page gives.
    if (error instanceof EngineRefused && error.status === 404) notFound();
    throw error;
  }
  const [{ controls }, { drafts }, outcomes] = await Promise.all([getControls(), getDrafts(), getOutcomes()]);
  const control = [...controls, ...drafts].find((entry) => entry.control_id === controlId);
  if (!control) notFound();
  return <HistoryView control={control} history={history} outcomes={outcomes} />;
}
