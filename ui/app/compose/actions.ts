"use server";
/**
 * The compose window's two Server Actions. Both are POSTs, and both pass the engine an explicit
 * allow-list of fields rather than whatever the form happened to carry.
 *
 * `file` is the one place besides the Run button that runs a control: it files the draft, then
 * runs it ONCE and sends the reader to the stored run - the same POST-then-redirect as the ask
 * page, so a reload can never run it again.
 */
import { redirect } from "next/navigation";
import { composeAccept, composeTurn, EngineRefused, runControlOnce } from "@/lib/api";
import type { AcceptRefused, ComposeTurnResponse } from "@/lib/types";

export interface AskState {
  response: ComposeTurnResponse | null;
  error: string | null;
}

export interface FileState {
  refusal: AcceptRefused | null;
  error: string | null;
  /** Which proposal this result belongs to, so asking again retires it. */
  turn: number;
}

const field = (formData: FormData, name: string) => String(formData.get(name) ?? "");

export async function ask(previous: AskState, formData: FormData): Promise<AskState> {
  try {
    const response = await composeTurn({
      prose: field(formData, "prose"),
      conversation: field(formData, "conversation"),
      template: field(formData, "template"),
    });
    return { response, error: null };
  } catch (error) {
    if (error instanceof EngineRefused) return { response: previous.response, error: error.message };
    throw error;
  }
}

export async function file(_previous: FileState, formData: FormData): Promise<FileState> {
  const turn = Number(field(formData, "turn"));
  const property = field(formData, "property");
  let filed;
  try {
    filed = await composeAccept({
      sentence: field(formData, "sentence"),
      control_id: field(formData, "control_id"),
      name: field(formData, "name"),
      template: field(formData, "template"),
      conversation: field(formData, "conversation"),
      property,
      evidence: field(formData, `evidence:${property}`),
    });
  } catch (error) {
    if (error instanceof EngineRefused) return { refusal: null, error: error.message, turn };
    throw error;
  }
  if (filed.status === 422) return { refusal: filed.body, error: null, turn };

  const { control_id, property: on, evidence } = filed.body;
  const run = await runControlOnce(control_id, on, evidence);
  // Outside any try: redirect() works by throwing, and must not be caught.
  redirect(`/runs/${encodeURIComponent(run.run_id)}`);
}
