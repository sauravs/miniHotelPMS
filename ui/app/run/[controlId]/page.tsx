/**
 * Ask a control a question. Running nothing on GET: everything read here is free (the spec, the
 * property list, the drafts), and the run itself is behind the button, as a POST (actions.ts).
 * The index's selection arrives in the query string and is validated, never trusted.
 */
import { notFound } from "next/navigation";
import { AskForm } from "@/components/AskForm";
import { selectionFrom } from "@/components/IndexView";
import { getControls, getDrafts, getProperties } from "@/lib/api";
import { startRun } from "./actions";

export const dynamic = "force-dynamic";

export default async function AskPage({
  params,
  searchParams,
}: {
  params: Promise<{ controlId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ controlId }, query, { controls }, properties] = await Promise.all([
    params,
    searchParams,
    getControls(),
    getProperties(),
  ]);
  const selection = selectionFrom(query, properties);
  // A draft belongs to the property it was composed for (slice 17).
  const { drafts } = await getDrafts(selection.property);
  // Reviewed controls first, exactly as the engine resolves an id: a draft can never shadow one.
  const control = [...controls, ...drafts].find((entry) => entry.control_id === controlId);
  if (!control) notFound();
  return <AskForm control={control} properties={properties} selection={selection} action={startRun} />;
}
