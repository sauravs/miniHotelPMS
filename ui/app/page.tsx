/**
 * The index: every control, its readiness per provider (criterion 10), and the evidence picker.
 * Three requests, all free - the spec, the properties and the drafts. Nothing here runs anything,
 * so this page is safe to load, reload and prefetch.
 */
import { IndexView, selectionFrom } from "@/components/IndexView";
import { getControls, getDrafts, getProperties } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Index({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [query, { controls }, properties, { drafts }] = await Promise.all([
    searchParams,
    getControls(),
    getProperties(),
    getDrafts(),
  ]);
  return (
    <IndexView
      controls={controls}
      properties={properties}
      selection={selectionFrom(query, properties)}
      drafts={drafts}
    />
  );
}
