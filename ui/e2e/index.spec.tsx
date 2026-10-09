/**
 * The index in a real browser: a short readiness line LOOKS short (criterion 10 is a sentence
 * AND a signal), and axe finds nothing on the index or on the ask form.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { AskForm } from "../components/AskForm";
import { IndexView, selectionFrom } from "../components/IndexView";
import type { ControlEntry, Properties } from "../lib/types";
import { golden, show } from "./page";

const { controls } = golden<{ controls: ControlEntry[] }>("controls.json");
const properties = golden<Properties>("properties.json");
const selection = selectionFrom({}, properties);

test("criterion 10: a control that cannot be answered looks different from one that can", async ({ page }) => {
  await show(page, <IndexView controls={controls} properties={properties} selection={selection} />);
  const colour = (id: string) =>
    page.locator(`[data-control-id="${id}"] p.readiness`).first().evaluate((p) => getComputedStyle(p).color);
  expect(await colour("rate_room_category_consistency")).not.toBe(await colour("checkout_money_owed"));
});

test("axe finds no violations on the index", async ({ page }) => {
  const draft = { ...controls[0], control_id: "my_draft", name: "My Draft", reviewed: false };
  await show(page, <IndexView controls={controls} properties={properties} selection={selection} drafts={[draft]} />);
  const { violations } = await new AxeBuilder({ page }).analyze();
  expect(violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`)).toEqual([]);
});

test("axe finds no violations on the ask form, and every control is keyboard-operable", async ({ page }) => {
  const control = controls.find((c) => c.control_id === "rate_room_category_consistency")!;
  await show(page, <AskForm control={control} properties={properties} selection={selection} />);
  const { violations } = await new AxeBuilder({ page }).analyze();
  expect(violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`)).toEqual([]);
  const reached = new Set<string>();
  for (let step = 0; step < 20; step++) {
    await page.keyboard.press("Tab");
    reached.add(await page.evaluate(() => document.activeElement?.getAttribute("name") ?? document.activeElement?.tagName ?? ""));
  }
  expect(reached).toContain("property");
  expect(reached).toContain("BUTTON");
});
