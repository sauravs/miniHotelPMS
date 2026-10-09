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
  const [query, { controls }, properties, { drafts }, compose] = await Promise.all([
    searchParams,
    getControls(),
    getProperties(),
    getDrafts(),
    getComposeState(),
  ]);
  return (
    <IndexView
      controls={controls}
      properties={properties}
      selection={selectionFrom(query, properties)}
      drafts={drafts}
      compose={compose.wired ? compose.proposer : null}
    />
  );
}
