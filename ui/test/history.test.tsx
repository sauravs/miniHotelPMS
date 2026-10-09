/**
 * The history page: every past run of one control, newest first, each re-readable for free.
 *
 * Criterion 8 one level up, and issue #35 on this surface: a row for a run that concluded nothing
 * carries `counts` - and must not show them. The engine's own history page got this wrong until
 * #36; the gate here is `concluded`, never the presence of `counts`.
 */
import { readdirSync } from "node:fs";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { HistoryView } from "@/components/HistoryView";
import type { ControlEntry, History } from "@/lib/types";
import { GOLDEN, golden, outcomes } from "./goldens";

afterEach(cleanup);

const textOf = (element: Element) => (element.textContent ?? "").replace(/\s+/g, " ").trim();
const { controls } = golden<{ controls: ControlEntry[] }>("controls.json");
const control = (id: string) => controls.find((c) => c.control_id === id)!;
const history = (id: string) => golden<History>(`history/${id}.json`);
const rows = (container: HTMLElement) => [...container.querySelectorAll<HTMLElement>("tr[data-run-id]")];

describe("the three states of a row", () => {
  it("a run that concluded nothing says so in the engine's words, and shows no counts (#35)", () => {
    const { runs } = history("ooo_room_protection");
    expect(runs[0].counts).toBeDefined(); // the trap, stated
    const { container } = render(
      <HistoryView control={control("ooo_room_protection")} history={history("ooo_room_protection")} outcomes={outcomes} />,
    );
    for (const row of rows(container)) {
      const text = textOf(row);
      expect(text).toContain("reached no conclusion");
      expect(text).not.toMatch(/\b0 VIOLATION\b/);
      expect(row.querySelector(".counts")).toBeNull();
    }
  });

  it("a blocked run says blocked and why, with no counts", () => {
    const h = history("resource_occupancy_consistency");
    const { container } = render(
      <HistoryView control={control("resource_occupancy_consistency")} history={h} outcomes={outcomes} />,
    );
    rows(container).forEach((row, index) => {
      expect(textOf(row)).toContain("blocked");
      expect(textOf(row)).toContain(h.runs[index].blocked!);
      expect(row.querySelector(".counts")).toBeNull();
    });
  });

  it("a run that concluded shows all four counts with the engine's badges, EXCLUDED its own", () => {
    const h = history("inactive_room_future_stay");
    const { container } = render(<HistoryView control={control("inactive_room_future_stay")} history={h} outcomes={outcomes} />);
    const concluded = rows(container).filter((_, index) => h.runs[index].concluded);
    expect(concluded.length).toBeGreaterThanOrEqual(2); // its 2026 runs; the 2024 ones are blocked
    concluded.forEach((row) => {
      const counts = h.runs.find((r) => r.run_id === row.getAttribute("data-run-id"))!.counts!;
      expect(textOf(row.querySelector(".counts")!)).toBe(
        outcomes.outcomes.map(({ outcome, badge }) => `${counts[outcome]} ${badge}`).join(" · "),
      );
    });
  });
});

describe("every row is a question, re-readable for free", () => {
  it("each run id links to its stored run, and the row names its evidence, instant and cost", () => {
    const h = history("checkout_money_owed");
    const { container } = render(<HistoryView control={control("checkout_money_owed")} history={h} outcomes={outcomes} />);
    rows(container).forEach((row, index) => {
      const run = h.runs[index];
      expect(row.querySelector("a")!.getAttribute("href")).toBe(`/runs/${run.run_id}`);
      const text = textOf(row);
      for (const value of [run.evidence_label, run.provider, run.as_of, String(run.calls)]) expect(text).toContain(value);
    });
  });

  it("names the control by the sentence it is", () => {
    render(<HistoryView control={control("checkout_money_owed")} history={history("checkout_money_owed")} outcomes={outcomes} />);
    expect(screen.getByText(control("checkout_money_owed").natural_language)).toBeTruthy();
  });

  it("explains, inline, that re-reading costs no provider call (R1)", () => {
    const { container } = render(
      <HistoryView control={control("checkout_money_owed")} history={history("checkout_money_owed")} outcomes={outcomes} />,
    );
    expect(textOf(container)).toContain("costs no provider call");
    expect(container.querySelectorAll("[title]")).toHaveLength(0);
  });
});

describe("an empty history is a first page, not a blank one", () => {
  it("says the control has not been run and offers to run it", () => {
    const { container } = render(
      <HistoryView control={control("checkout_money_owed")} history={{ control_id: "checkout_money_owed", runs: [] }} outcomes={outcomes} />,
    );
    expect(textOf(container)).toContain("has not been run");
    expect(container.querySelector("table")).toBeNull();
    expect(container.querySelector('a[href="/run/checkout_money_owed"]')).not.toBeNull();
  });
});

describe("parity over every history golden", () => {
  const names = readdirSync(GOLDEN + "history").sort();
  it("there is one per control", () => expect(names).toHaveLength(controls.length));

  it.each(names)("%s", (name) => {
    const h = golden<History>(`history/${name}`);
    const { container } = render(<HistoryView control={control(h.control_id)} history={h} outcomes={outcomes} />);
    const rendered = rows(container);
    expect(rendered.map((r) => r.getAttribute("data-run-id"))).toEqual(h.runs.map((r) => r.run_id));
    rendered.forEach((row, index) => {
      const run = h.runs[index];
      expect(row.querySelector(".counts") !== null).toBe(run.concluded && run.blocked === null);
      if (run.headline) expect(textOf(row)).toContain(run.headline);
    });
  });
});

describe("slice 16 - history groups by the rule that judged each run (V3)", () => {
  it("every golden row is under a header naming its version and digest", () => {
    const h = history("checkout_money_owed");
    const { container } = render(<HistoryView control={control("checkout_money_owed")} history={h} outcomes={outcomes} />);
    const groups = [...container.querySelectorAll("tbody[data-policy]")];
    expect(groups).toHaveLength(1);
    expect(textOf(groups[0].querySelector("tr.policy")!)).toContain(`Judged under v${h.runs[0].policy_version}`);
  });

  it("v2 and v3 runs are two groups, newest first, and a pre-v3 run says version not recorded", () => {
    const base = history("checkout_money_owed").runs[0];
    const h: History = {
      control_id: "checkout_money_owed",
      runs: [
        { ...base, run_id: "v3run", policy_version: 3, policy_digest: "sha256:" + "b".repeat(64) },
        { ...base, run_id: "v2run", policy_version: 2, policy_digest: "sha256:" + "a".repeat(64) },
        { ...base, run_id: "oldrun", policy_version: null, policy_digest: null },
      ],
    };
    const { container } = render(<HistoryView control={control("checkout_money_owed")} history={h} outcomes={outcomes} />);
    const headers = [...container.querySelectorAll("tbody[data-policy] tr.policy")].map(textOf);
    expect(headers).toHaveLength(3);
    expect(headers[0]).toContain("Judged under v3");
    expect(headers[0]).toContain("bbbbbbbbbbbb");
    expect(headers[1]).toContain("Judged under v2");
    expect(headers[2]).toContain("Version not recorded");
    expect(rows(container).map((r) => r.getAttribute("data-run-id"))).toEqual(["v3run", "v2run", "oldrun"]);
  });

  it("one version with two digests is two groups, so an unbumped edit cannot hide", () => {
    const base = history("checkout_money_owed").runs[0];
    const h: History = {
      control_id: "checkout_money_owed",
      runs: [
        { ...base, run_id: "edited", policy_version: 2, policy_digest: "sha256:" + "c".repeat(64) },
        { ...base, run_id: "reviewed", policy_version: 2, policy_digest: "sha256:" + "a".repeat(64) },
      ],
    };
    const { container } = render(<HistoryView control={control("checkout_money_owed")} history={h} outcomes={outcomes} />);
    expect(container.querySelectorAll("tbody[data-policy]")).toHaveLength(2);
  });
});
