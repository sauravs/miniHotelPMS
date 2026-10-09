/**
 * Criterion 2's other two signals, in a real browser: HUE and BORDER. jsdom computes no styles,
 * so this is the only layer that can assert them honestly.
 *
 * And an axe pass over each run-page state: concluded, concluded-nothing, and blocked.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { RunView } from "../components/RunView";
import { Verdict } from "../components/Verdict";
import type { OutcomeName, Outcomes, RunPayload } from "../lib/types";
import { golden, show } from "./page";

const outcomes = golden<Outcomes>("outcomes.json");
const run = (name: string) => golden<RunPayload>(`run/${name}`);
const ALL: OutcomeName[] = ["PASS", "FAIL", "UNKNOWN", "EXCLUDED"];

/** One REAL verdict of each outcome, taken from the matrix rather than made up. */
function oneOfEach() {
  const found = new Map<OutcomeName, RunPayload["verdicts"][number]>();
  for (const name of ["checkout_unrefunded_credit", "inactive_room_future_stay", "room_capacity_compliance"]) {
    for (const verdict of run(`${name}.sandbox.sandbox2026.json`).verdicts) {
      if (!found.has(verdict.outcome)) found.set(verdict.outcome, verdict);
    }
  }
  return ALL.map((outcome) => found.get(outcome)!);
}

test("criterion 2: the four verdicts have four different border styles and four different hues", async ({ page }) => {
  const verdicts = oneOfEach();
  expect(verdicts.map((v) => v.outcome)).toEqual(ALL);
  await show(
    page,
    <>
      {verdicts.map((verdict) => (
        <Verdict key={verdict.outcome} verdict={verdict} wording={outcomes.outcomes.find((o) => o.outcome === verdict.outcome)!} />
      ))}
    </>,
  );
  const computed = await page.locator("article.verdict").evaluateAll((blocks) =>
    blocks.map((b) => [getComputedStyle(b).borderLeftStyle, getComputedStyle(b).borderLeftColor]),
  );
  expect(computed).toHaveLength(4);
  expect(new Set(computed.map(([style]) => style)).size).toBe(4);
  expect(new Set(computed.map(([, colour]) => colour)).size).toBe(4);
  expect(computed.map(([style]) => style)).not.toContain("none");
});

test("criterion 2: the tiles carry the same two signals as the verdicts", async ({ page }) => {
  await show(page, <RunView run={run("checkout_money_owed.sandbox.sandbox2026.json")} outcomes={outcomes} />);
  const tiles = await page.locator("ul.tiles > li").evaluateAll((items) =>
    items.map((li) => [getComputedStyle(li).borderLeftStyle, getComputedStyle(li).borderLeftColor]),
  );
  expect(tiles).toHaveLength(4);
  expect(new Set(tiles.map(([style]) => style)).size).toBe(4);
  expect(new Set(tiles.map(([, colour]) => colour)).size).toBe(4);
});

test("every disclosure is reachable and operable from the keyboard", async ({ page }) => {
  await show(page, <RunView run={run("inactive_room_future_stay.sandbox.sandbox2026.json")} outcomes={outcomes} />);
  const summaries = page.locator("summary");
  const total = await summaries.count();
  expect(total).toBeGreaterThan(2);
  let reached = 0;
  for (let step = 0; step < 400 && reached < total; step++) {
    await page.keyboard.press("Tab");
    if (await page.evaluate(() => document.activeElement?.tagName === "SUMMARY")) reached++;
  }
  expect(reached).toBe(total);
  // A closed group opens with Enter: collapsing is not omitting.
  const closed = page.locator("details.group.EXCLUDED");
  await expect(closed).not.toHaveAttribute("open", "");
  await closed.locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(closed).toHaveAttribute("open", "");
});

for (const [state, name] of [
  ["concluded", "inactive_room_future_stay.sandbox.sandbox2026.json"],
  ["concluded nothing", "ooo_room_protection.sandbox.sandbox2026.json"],
  ["blocked", "resource_occupancy_consistency.sandbox.sandbox2026.json"],
  ["a violation", "checkout_unrefunded_credit.sandbox.sandbox2026.json"],
] as const) {
  test(`axe finds no violations on a run that ${state}`, async ({ page }) => {
    await show(page, <RunView run={run(name)} outcomes={outcomes} />);
    const { violations } = await new AxeBuilder({ page }).analyze();
    expect(violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`)).toEqual([]);
  });
}
