/** The findings queue in a real browser (slice 18): axe on a queue with a task and on an empty one. */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { QueueView } from "../components/QueueView";
import type { Outcomes, Properties, Queue } from "../lib/types";
import { golden, show } from "./page";

const outcomes = golden<Outcomes>("outcomes.json");
const properties = golden<Properties>("properties.json");

for (const [state, name] of [
  ["one pending task and every control's latest run", "sandbox"],
  ["nothing run and nothing raised", "empty.sandbox"],
] as const) {
  test(`axe finds no violations on a queue with ${state}`, async ({ page }) => {
    await show(page, <QueueView queue={golden<Queue>(`actions/${name}.json`)} properties={properties} outcomes={outcomes} />);
    const { violations } = await new AxeBuilder({ page }).analyze();
    expect(violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`)).toEqual([]);
  });
}

test("a task's two moves are reachable by keyboard", async ({ page }) => {
  await show(page, <QueueView queue={golden<Queue>("actions/sandbox.json")} properties={properties} outcomes={outcomes} />);
  const buttons = page.locator("article.task button");
  await expect(buttons).toHaveText(["Mark done", "Dismiss"]);
  await buttons.first().focus();
  await expect(buttons.first()).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(buttons.nth(1)).toBeFocused();
});
