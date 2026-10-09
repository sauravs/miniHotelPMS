/** The compose window in a real browser: axe on every state it can be in. */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { ComposeView } from "../components/ComposeView";
import { selectionFrom } from "../components/IndexView";
import type { AcceptRefused, ComposeState, ComposeTurnResponse, Properties } from "../lib/types";
import { golden, show } from "./page";

const properties = golden<Properties>("properties.json");
const selection = selectionFrom({}, properties);
const wired = golden<ComposeState>("compose/wired.json");

const states: [string, ComposeState, ComposeTurnResponse | null, AcceptRefused | null][] = [
  ["switched off", golden<ComposeState>("compose/off.json"), null, null],
  ["waiting for a question", wired, null, null],
  ["a sentence that compiles", wired, golden("compose/compiles.json"), null],
  ["a refusal", wired, golden("compose/refused.json"), null],
  ["a question", wired, golden("compose/question.json"), null],
  ["a refused filing", wired, golden("compose/compiles.json"), golden("compose/accept-refused.json")],
];

for (const [name, state, response, refusal] of states) {
  test(`axe finds no violations on compose: ${name}`, async ({ page }) => {
    await show(
      page,
      <ComposeView state={state} properties={properties} selection={selection} response={response} refusal={refusal} />,
    );
    const { violations } = await new AxeBuilder({ page }).analyze();
    expect(violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`)).toEqual([]);
  });
}
