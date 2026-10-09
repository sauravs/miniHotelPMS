"use client";
/**
 * The compose window, wired. The only client component in the UI, and deliberately thin: it
 * holds the two Server Actions' results and hands them to the pure ComposeView.
 *
 * Both actions are POSTs (trap 4). It imports the ACTIONS, never lib/api - nothing here can
 * issue a request of its own - and both buttons are disabled while one is pending, so a double
 * click cannot file twice or run twice.
 */
import { useActionState } from "react";
import { ask, file } from "@/app/compose/actions";
import type { ComposeState, Properties } from "@/lib/types";
import { ComposeView } from "./ComposeView";
import type { Selection } from "./IndexView";

export function ComposeClient({
  state,
  properties,
  selection,
}: {
  state: ComposeState;
  properties: Properties;
  selection: Selection;
}) {
  const [asked, askAction, asking] = useActionState(ask, { response: null, error: null });
  const [filed, fileAction, filing] = useActionState(file, { refusal: null, error: null, turn: -1 });
  const turns = asked.response?.transcript.length ?? state.transcript.length;
  // A refusal belongs to the proposal it was filed from; asking again retires it.
  const current = filed.turn === turns;
  return (
    <ComposeView
      state={state}
      properties={properties}
      selection={selection}
      response={asked.response}
      refusal={current ? filed.refusal : null}
      error={(current ? filed.error : null) ?? asked.error}
      askAction={askAction}
      fileAction={(formData) => {
        formData.set("turn", String(turns));
        fileAction(formData);
      }}
      pending={asking || filing}
    />
  );
}
