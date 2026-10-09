"use server";
/**
 * Moving a task in the findings queue (slice 18). A Server Action, so it is a POST: a task is
 * marked done or dismissed only when a person presses the button, never by a page load, a
 * prefetch or a re-firing effect. Afterwards the reader is sent back to the queue, which is a
 * free read and safe to reload.
 *
 * It writes the engine's own store and nothing else. The engine never writes to a PMS.
 */
import { redirect } from "next/navigation";
import { moveAction } from "@/lib/api";

export async function moveTask(formData: FormData): Promise<void> {
  const actionId = String(formData.get("action_id") ?? "");
  const property = String(formData.get("property") ?? "");
  const state = String(formData.get("state") ?? "");
  const moved = await moveAction(actionId, property, state);
  redirect(`/queue?property=${encodeURIComponent(moved.property)}`);
}
