/**
 * The index: every control, its readiness per provider (criterion 10), and the evidence picker.
 * Four requests, all free - the spec, the properties, the drafts and whether compose is wired. Nothing here runs anything,
 * so this page is safe to load, reload and prefetch.
 */
import { IndexView, selectionFrom } from "@/components/IndexView";
import { getComposeState, getControls, getDrafts, getProperties } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Index({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [query, { controls }, properties, compose] = await Promise.all([
    searchParams,
    getControls(),
    getProperties(),
    getComposeState(),
  ]);
  const selection = selectionFrom(query, properties);
  // Drafts are per property since slice 17: the selected property's, and nobody else's.
  const { drafts } = await getDrafts(selection.property);
  return (
    <IndexView
      controls={controls}
      properties={properties}
      selection={selection}
      drafts={drafts}
      compose={compose.wired ? compose.proposer : null}
    />
  );
}
