"use server";
/**
 * The one place a control is run. A Server Action, so it is a POST.
 *
 * TRAP 4. `GET /api/run/` spends provider calls and writes the store. A GET-driven fetch in this
 * UI could be repeated by things nobody decided: StrictMode double-invoking an effect, a refetch
 * on window focus, a link prefetch. A POST from a button is none of those. After it, the reader
 * is sent to `/runs/<run_id>`, which re-reads the stored run for free and can be reloaded,
 * bookmarked and prefetched without running anything again.
 */
import { redirect } from "next/navigation";
import { runControlOnce } from "@/lib/api";

export async function startRun(formData: FormData): Promise<void> {
  const controlId = String(formData.get("control_id") ?? "");
  const property = String(formData.get("property") ?? "");
  const evidence = String(formData.get(`evidence:${property}`) ?? "");
  // The ids reach the engine URL-encoded and the engine refuses one it does not know by name.
  const run = await runControlOnce(controlId, property, evidence);
  redirect(`/runs/${encodeURIComponent(run.run_id)}`);
}
