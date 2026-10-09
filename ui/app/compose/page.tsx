/**
 * The compose window. Reading its state is free; everything that writes is a POST behind a
 * button. When the engine has no proposer wired, the page says so and renders no form at all.
 */
import { ComposeClient } from "@/components/ComposeClient";
import { ComposeView } from "@/components/ComposeView";
import { selectionFrom } from "@/components/IndexView";
import { getComposeState, getProperties } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ComposePage() {
  const [state, properties] = await Promise.all([getComposeState(), getProperties()]);
  const selection = selectionFrom({}, properties);
  if (!state.wired) return <ComposeView state={state} properties={properties} selection={selection} />;
  return <ComposeClient state={state} properties={properties} selection={selection} />;
}
