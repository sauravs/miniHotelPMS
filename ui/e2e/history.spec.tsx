/** The history page in a real browser: axe on a populated history and on an empty one. */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { HistoryView } from "../components/HistoryView";
import type { ControlEntry, History, Outcomes } from "../lib/types";
import { golden, show } from "./page";

const outcomes = golden<Outcomes>("outcomes.json");
const { controls } = golden<{ controls: ControlEntry[] }>("controls.json");
const control = (id: string) => controls.find((c) => c.control_id === id)!;

for (const [state, id, empty] of [
  ["all three row states", "inactive_room_future_stay", false],
  ["rows that concluded nothing", "ooo_room_protection", false],
  ["no runs yet", "checkout_money_owed", true],
] as const) {
  test(`axe finds no violations on a history with ${state}`, async ({ page }) => {
    const history = empty ? { control_id: id, runs: [] } : golden<History>(`history/${id}.json`);
    await show(page, <HistoryView control={control(id)} history={history} outcomes={outcomes} />);
    const { violations } = await new AxeBuilder({ page }).analyze();
    expect(violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`)).toEqual([]);
  });
}
