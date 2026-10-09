/**
 * The findings queue (slice 18), rendered from the engine's own answers in fixtures/api/actions/.
 *
 * Three things this surface must get right, each one a way the page could look fine and lie:
 *
 *   - an EMPTY queue is not an all-clear. Beside the tasks, every control's latest run says
 *     whether it concluded - and "not run", "blocked" and "reached no conclusion" are all said;
 *   - a task's words are the engine's: the VIOLATION badge from /api/outcomes, the reason with its
 *     money verbatim (R9), severity and audience from the rule;
 *   - only a pending task can be moved, and a move is a form, never a link.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { QueueView } from "@/components/QueueView";
import type { Properties, Queue } from "@/lib/types";
import { golden, outcomes } from "./goldens";

afterEach(cleanup);

const textOf = (element: Element) => (element.textContent ?? "").replace(/\s+/g, " ").trim();
const properties = golden<Properties>("properties.json");
const queue = (name: string) => golden<Queue>(`actions/${name}.json`);
const show = (q: Queue) => render(<QueueView queue={q} properties={properties} outcomes={outcomes} />).container;

describe("a queue with the one real VIOLATION in it (007004348, unrefunded credit)", () => {
  for (const property of ["sandbox", "demo"]) {
    it(`${property}: one pending task, in the engine's words`, () => {
      const q = queue(property);
      const container = show(q);
      const tasks = [...container.querySelectorAll<HTMLElement>("article.task")];
      expect(tasks).toHaveLength(1);
      const [record] = q.records;
      const text = textOf(tasks[0]);
      expect(tasks[0].getAttribute("data-action-id")).toBe(record.action_id);
      expect(tasks[0].querySelector(".badge")!.textContent).toBe(
        outcomes.outcomes.find((o) => o.outcome === "FAIL")!.badge,
      );
      expect(text).toContain("007004348");
      expect(text).toContain(record.reason); // verbatim, money and currency together
      expect(text).toContain("-490.75 ILS");
      expect(text).toContain("severity medium");
      expect(text).toContain("for finance");
      expect(tasks[0].querySelector("a")!.getAttribute("href")).toBe(
        `/runs/${record.raised.run_id}?property=${property}`,
      );
    });
  }

  it("offers exactly two moves, each a form carrying the task, its property and the state", () => {
    const q = queue("sandbox");
    const forms = [...show(q).querySelectorAll("article.task form")];
    expect(forms).toHaveLength(2);
    const fields = forms.map((form) =>
      Object.fromEntries([...form.querySelectorAll("input")].map((i) => [i.name, i.value])),
    );
    expect(fields).toEqual([
      { action_id: q.records[0].action_id, property: "sandbox", state: "done" },
      { action_id: q.records[0].action_id, property: "sandbox", state: "dismissed" },
    ]);
  });

  it("a closed task is listed apart, says who closed it and when, and offers no move", () => {
    const q = queue("sandbox");
    const closed: Queue = {
      ...q,
      pending: 0,
      records: [{ ...q.records[0], state: "done", state_changed_at: "2026-10-09T09:30:00+03:00", state_changed_by: "operator" }],
    };
    const container = show(closed);
    const section = container.querySelector("details[data-closed]")!;
    expect(textOf(section)).toContain("Marked done by operator at 2026-10-09T09:30:00+03:00");
    expect(container.querySelectorAll("form")).toHaveLength(0);
    // And the to-do list is empty, which is still not an all-clear.
    expect(textOf(container.querySelector("[data-empty]")!)).toContain("not an all-clear");
  });
});

describe("the coverage table is what stops an empty queue reading as an all-clear", () => {
  it("every control has a row, with the engine's status label and sentence", () => {
    const q = queue("sandbox");
    const rows = [...show(q).querySelectorAll<HTMLElement>("tr[data-control-id]")];
    expect(rows.map((r) => r.getAttribute("data-control-id"))).toEqual(q.controls.map((c) => c.control_id));
    rows.forEach((row, index) => {
      const control = q.controls[index];
      expect(row.getAttribute("data-status")).toBe(control.status);
      expect(textOf(row)).toContain(control.label);
      expect(textOf(row)).toContain(control.headline);
    });
  });

  it("names the controls that reached no conclusion, the blocked one, and never shows counts", () => {
    const container = show(queue("sandbox"));
    const row = (id: string) => textOf(container.querySelector(`tr[data-control-id="${id}"]`)!);
    expect(row("ooo_room_protection")).toContain("reached no conclusion");
    expect(row("resource_occupancy_consistency")).toContain("blocked");
    expect(textOf(container)).not.toMatch(/\b0 VIOLATION\b/);
  });

  it("an untouched store: nothing to do, not an all-clear, and every control not run here", () => {
    const q = queue("empty.sandbox");
    const container = show(q);
    expect(textOf(container.querySelector("[data-empty]")!)).toContain(
      "Nothing is waiting in this queue - and that is not an all-clear.",
    );
    const statuses = [...container.querySelectorAll("tr[data-control-id]")].map((r) => r.getAttribute("data-status"));
    expect(new Set(statuses)).toEqual(new Set(["not_run"]));
    expect(statuses).toHaveLength(q.controls.length);
    expect(container.querySelectorAll("form")).toHaveLength(0);
  });
});

describe("the page states what it cannot promise", () => {
  it("an in-memory queue says it is lost on restart (brief §8.8)", () => {
    const container = show(queue("sandbox"));
    expect(textOf(container.querySelector("[data-persistence]")!)).toContain("lost on restart");
  });

  it("help is inline, never a title tooltip", () => {
    const container = show(queue("sandbox"));
    expect(container.querySelectorAll("[title]")).toHaveLength(0);
    expect(textOf(container)).toContain("A run never closes a task.");
  });
});

describe("email delivery, when the engine has a notifier wired (slice 19)", () => {
  // CONSTRUCTED: the goldens are built with no notifier, which is the default, so the delivery
  // fields are added here in the exact shape the engine's wired payload carries.
  const wired = (delivery: NonNullable<Queue["records"][0]["delivery"]>): Queue => {
    const q = queue("sandbox");
    return { ...q, email: { wired: true, via: "smtp" }, records: [{ ...q.records[0], delivery }] };
  };

  it("an unwired engine says nobody is emailed, and no task carries a delivery line", () => {
    const container = show(queue("sandbox"));
    expect(textOf(container.querySelector("[data-email]")!)).toContain("Email is not wired");
    expect(container.querySelector(".delivery")).toBeNull();
  });

  it("a sent task says when, and to which audience", () => {
    const container = show(wired({ channel: "email", sent_at: "2026-10-09T09:30:00+03:00", note: null }));
    expect(textOf(container.querySelector("[data-email]")!)).toContain("Email is wired (smtp)");
    expect(textOf(container.querySelector(".delivery")!)).toBe("Emailed to finance at 2026-10-09T09:30:00+03:00.");
  });

  it("an unsent task says why, in the engine's words", () => {
    const container = show(wired({ channel: null, sent_at: null, note: "no route configured for audience finance" }));
    expect(textOf(container.querySelector(".delivery")!)).toBe("Not emailed: no route configured for audience finance.");
  });
});
