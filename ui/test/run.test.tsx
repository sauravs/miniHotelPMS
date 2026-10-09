/**
 * The run page, re-proving the criteria the engine's tests prove about the OTHER surface.
 * Those tests say nothing about this one; a React UI that does not re-prove them is a React UI
 * that silently fails the product.
 *
 *   criterion 2   UNKNOWN is told apart from FAIL by WORDING, asserted on text with all styling
 *                 stripped. (Hue and border are asserted in a real browser - e2e/ - because jsdom
 *                 computes no styles and pretending otherwise would be a test of nothing.)
 *   criterion 3   every verdict traces to its fields: name, value WITH unit, provenance, gap.
 *   criterion 8   a run that concluded nothing says so and shows NO tiles - even though its
 *                 payload carries `counts` (trap 1).
 *   EXCLUDED      is its own tile and its own group, never folded into PASS.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { RunView } from "@/components/RunView";
import { Verdict } from "@/components/Verdict";
import type { OutcomeName, RunPayload, VerdictPayload } from "@/lib/types";
import { outcomes, run, stored } from "./goldens";

afterEach(cleanup);

/** The page as a reader with no colour, no borders and no CSS receives it. `text_of()`'s twin. */
const textOf = (element: Element) => (element.textContent ?? "").replace(/\s+/g, " ").trim();

const tiles = () => screen.queryByRole("list", { name: "How many records reached each answer" });

const wordingOf = (outcome: OutcomeName) => outcomes.outcomes.find((o) => o.outcome === outcome)!;

describe("criterion 8 - a run that concluded nothing says so, and shows no counts", () => {
  it("ooo_room_protection: counts ARE in the payload, and still no tile is rendered (trap 1)", () => {
    const payload = run("ooo_room_protection.sandbox.sandbox2026.json");
    // The trap, stated: the payload is a tempting one.
    expect(payload.counts).toEqual({ PASS: 0, FAIL: 0, UNKNOWN: 0, EXCLUDED: 28, total: 28 });
    expect(payload.coverage.concluded).toBe(false);

    const { container } = render(<RunView run={payload} outcomes={outcomes} />);
    expect(tiles()).toBeNull();
    expect(textOf(container)).toContain("reached no conclusion");
    expect(textOf(container)).not.toMatch(/\b0 VIOLATION\b/);
  });

  it("a blocked run has no tiles and says it could not run, not that it concluded nothing", () => {
    const payload = run("resource_occupancy_consistency.sandbox.sandbox2026.json");
    expect(payload.blocked).toBeTruthy();
    const { container } = render(<RunView run={payload} outcomes={outcomes} />);
    expect(tiles()).toBeNull();
    expect(textOf(container)).toContain("could not run");
    expect(textOf(container)).toContain(payload.blocked!);
  });

  it("a run that did conclude shows its four tiles, EXCLUDED its own", () => {
    const payload = run("inactive_room_future_stay.sandbox.sandbox2026.json");
    expect(payload.coverage.concluded).toBe(true);
    render(<RunView run={payload} outcomes={outcomes} />);
    const items = within(tiles()!).getAllByRole("listitem");
    expect(items.map((item) => textOf(item))).toEqual(
      outcomes.outcomes.map(({ outcome, badge }) => `${payload.counts![outcome]}${badge}`),
    );
  });
});

describe("criterion 3 - a verdict traces to its fields", () => {
  it("the overpaid folio: record, field, amount WITH its currency, and the call it came from", () => {
    const payload = run("checkout_unrefunded_credit.sandbox.sandbox2026.json");
    const { container } = render(<RunView run={payload} outcomes={outcomes} />);
    const block = container.querySelector('[data-record-id="007004348"]')!;
    expect(block.getAttribute("data-outcome")).toBe("FAIL");
    const text = textOf(block);
    expect(text).toContain("-490.75 ILS");
    expect(text).toContain("folio.balance_due");
    expect(text).toMatch(/pms:\S+/);
  });

  it("an UNKNOWN names the field it could not establish and why", () => {
    const payload = run("room_capacity_compliance.sandbox.sandbox2026.json");
    const { container } = render(<RunView run={payload} outcomes={outcomes} />);
    const unknown = container.querySelector('[data-outcome="UNKNOWN"]')!;
    const gap = payload.verdicts.find((v) => v.outcome === "UNKNOWN")!.evidence.find((l) => !l.known)!;
    expect(textOf(unknown)).toContain(gap.field);
    expect(textOf(unknown)).toContain(gap.reason!);
  });

  it("every known value on every run is on the page exactly as the engine wrote it", () => {
    for (const name of ["checkout_money_owed.sandbox.sandbox2026.json", "checkout_money_owed.demo.demo2026.json"]) {
      const payload = run(name);
      const { container } = render(<RunView run={payload} outcomes={outcomes} />);
      const cells = new Set([...container.querySelectorAll("table.evidence td")].map((td) => td.textContent));
      for (const line of payload.verdicts.flatMap((v) => v.evidence)) {
        if (line.known) expect(cells).toContain(line.value);
      }
      cleanup();
    }
  });
});

describe("criterion 2 - the four answers differ in WORDS, with all styling stripped", () => {
  const one = (outcome: OutcomeName): VerdictPayload => ({
    record_id: "007003199",
    outcome,
    means: wordingOf(outcome).means,
    reason: "because",
    evidence: [],
  });

  it("each outcome's text is different, and UNKNOWN reads as neither a pass nor a failure", () => {
    const texts = (["PASS", "FAIL", "UNKNOWN", "EXCLUDED"] as const).map((outcome) => {
      const { container } = render(<Verdict verdict={one(outcome)} wording={wordingOf(outcome)} />);
      const text = textOf(container);
      cleanup();
      return text;
    });
    expect(new Set(texts).size).toBe(4);
    expect(texts[2]).toContain("not a pass and not a failure");
    expect(texts[3]).toContain("This is not a pass");
    expect(texts[1]).toContain("VIOLATION");
    expect(texts[2]).toContain("NO ANSWER");
  });

  it("the glossary is the engine's wording, every badge and every meaning", () => {
    const { container } = render(
      <RunView run={run("inactive_room_future_stay.sandbox.sandbox2026.json")} outcomes={outcomes} />,
    );
    const glossary = textOf(container.querySelector("details.glossary")!);
    for (const { badge, means } of outcomes.outcomes) {
      expect(glossary).toContain(badge);
      expect(glossary).toContain(means);
    }
  });

  it("no help is hidden in a title attribute - invisible to touch, stripped from text", () => {
    const { container } = render(
      <RunView run={run("inactive_room_future_stay.sandbox.sandbox2026.json")} outcomes={outcomes} />,
    );
    expect(container.querySelectorAll("[title]")).toHaveLength(0);
  });
});

describe("grouping - a work queue that hides nothing", () => {
  it("groups read violations, gaps, passes, then not-applicable; the first two open", () => {
    const payload = run("inactive_room_future_stay.sandbox.sandbox2026.json");
    const { container } = render(<RunView run={payload} outcomes={outcomes} />);
    const groups = [...container.querySelectorAll("details.group")];
    const present = outcomes.group_order.filter((o) => payload.verdicts.some((v) => v.outcome === o));
    expect(groups.map((g) => g.id)).toEqual(present.map((o) => `verdicts-${o}`));
    for (const group of groups) {
      const outcome = group.id.replace("verdicts-", "") as OutcomeName;
      expect((group as HTMLDetailsElement).open).toBe(wordingOf(outcome).open);
    }
  });

  it("a tile with records links to its group; a zero links nowhere", () => {
    const payload = run("checkout_money_owed.sandbox.sandbox2026.json");
    render(<RunView run={payload} outcomes={outcomes} />);
    for (const item of within(tiles()!).getAllByRole("listitem")) {
      const outcome = item.className as OutcomeName;
      const link = item.querySelector("a");
      if (payload.counts![outcome]) expect(link?.getAttribute("href")).toBe(`#verdicts-${outcome}`);
      else expect(link).toBeNull();
    }
  });
});

export type { RunPayload };

describe("F7's line on a stored run - when this control runs next", () => {
  it("a stored run carries no plan; the one served beside it is shown, word for word as live", () => {
    const live = run("checkout_money_owed.sandbox.sandbox2026.json");
    const past = stored(`${live.run_id}.json`);
    expect(past.execution).toBeUndefined();
    const { container } = render(<RunView run={past} outcomes={outcomes} plan={live.execution} />);
    expect(textOf(container)).toContain(live.execution!.headline);
  });

  it("with neither, there is simply no plan line - nothing is invented", () => {
    const live = run("checkout_money_owed.sandbox.sandbox2026.json");
    const { container } = render(<RunView run={stored(`${live.run_id}.json`)} outcomes={outcomes} />);
    expect(textOf(container)).not.toContain(live.execution!.headline);
  });
});

describe("slice 16 - which rule judged it (V3)", () => {
  it("a run names the version and the digest of the rule that judged it", () => {
    const payload = run("checkout_money_owed.sandbox.sandbox2026.json");
    expect(payload.policy_version).toBe(2);
    const { container } = render(<RunView run={payload} outcomes={outcomes} />);
    const line = textOf(container.querySelector(".policy")!);
    expect(line).toContain("Judged under v2 of this rule");
    expect(line).toContain(payload.policy_digest!.slice("sha256:".length, "sha256:".length + 12));
  });

  it("a stored run says the same as the live one", () => {
    const live = run("checkout_money_owed.sandbox.sandbox2026.json");
    const again = stored(`${live.run_id}.json`);
    expect([again.policy_version, again.policy_digest]).toEqual([live.policy_version, live.policy_digest]);
  });

  it("a run stored before rules carried a version says so, and never claims today's", () => {
    const old: RunPayload = {
      ...run("checkout_money_owed.sandbox.sandbox2026.json"),
      policy_version: null,
      policy_digest: null,
    };
    const { container } = render(<RunView run={old} outcomes={outcomes} />);
    const line = textOf(container.querySelector(".policy")!);
    expect(line).toContain("Version not recorded");
    expect(line).not.toContain("Judged under");
  });
});
