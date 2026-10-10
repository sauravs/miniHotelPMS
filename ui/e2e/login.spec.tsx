/** The sign-in page (v3 slice 24) in a real browser: axe on every state it can be in. */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { LoginView } from "../components/LoginView";
import { show } from "./page";

const states = [
  ["authentication off", { enabled: false, identity: null, failed: false }],
  ["signed out", { enabled: true, identity: null, failed: false }],
  ["a failed sign-in", { enabled: true, identity: null, failed: true }],
  ["signed in", { enabled: true, identity: { user: "alice", property: "sandbox" }, failed: false }],
] as const;

for (const [name, props] of states) {
  test(`axe finds no violations on sign-in: ${name}`, async ({ page }) => {
    await show(page, <LoginView {...props} />);
    const { violations } = await new AxeBuilder({ page }).analyze();
    expect(violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`)).toEqual([]);
  });
}
