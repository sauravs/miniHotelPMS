/**
 * One property's findings queue (slice 18). Everything read here is free - the queue and the
 * property list - and the only write is behind a button, as a POST (actions.ts).
 */
import { QueueView } from "@/components/QueueView";
import { getOutcomes, getProperties, getQueue } from "@/lib/api";
import { moveTask } from "./actions";

export const dynamic = "force-dynamic";

export default async function QueuePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = await searchParams;
  // An absent or unknown property is the engine's to resolve, and the payload says which
  // property it answered for - exactly as the history page does.
  const property = [query.property].flat()[0] ?? "";
  const [queue, properties, outcomes] = await Promise.all([getQueue(property), getProperties(), getOutcomes()]);
  return <QueueView queue={queue} properties={properties} outcomes={outcomes} action={moveTask} />;
}
