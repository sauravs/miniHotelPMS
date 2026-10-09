/**
 * The index, re-proving criterion 10 on this surface: readiness per control PER PROVIDER, and a
 * control that cannot be answered says what to connect. Finding F8: v1 had every ingredient and
 * surfaced none of it, so nothing told a customer which controls their PMS could answer - and
 * "connect your housekeeping system to enable this" is the sentence that makes UNKNOWN a product
 * path rather than a limitation.
 *
 * Also: the evidence picker (every property x capture, the current one announced), a selection
 * that never trusts the URL, and drafts kept visibly apart from the reviewed controls.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { AskForm } from "@/components/AskForm";
import { IndexView, selectionFrom } from "@/components/IndexView";
import type { ControlEntry, Properties } from "@/lib/types";
import { golden } from "./goldens";

afterEach(cleanup);

const { controls } = golden<{ controls: ControlEntry[] }>("controls.json");
const properties = golden<Properties>("properties.json");
const textOf = (element: Element) => (element.textContent ?? "").replace(/\s+/g, " ").trim();
const DEFAULT = selectionFrom({}, properties);

const card = (container: HTMLElement, id: string) =>
  container.querySelector<HTMLElement>(`[data-control-id="${id}"]`)!;

describe("criterion 10 - readiness per control per provider", () => {
  it("lists every reviewed control, in spec order, each with the sentence it IS", () => {
    const { container } = render(<IndexView controls={controls} properties={properties} selection={DEFAULT} />);
    const listed = [...container.querySelectorAll("[data-control-id]")].map((c) => c.getAttribute("data-control-id"));
    expect(listed).toEqual(controls.map((c) => c.control_id));
    expect(textOf(container)).toContain("A reservation cannot be closed while the guest still owes money.");
  });

  it("every control shows one readiness line for every provider, as the engine worded it", () => {
    const { container } = render(<IndexView controls={controls} properties={properties} selection={DEFAULT} />);
    for (const control of controls) {
      const lines = [...card(container, control.control_id).querySelectorAll("p.readiness")].map(textOf);
      expect(lines).toEqual(control.readiness.map((report) => report.headline));
      expect(control.readiness.length).toBeGreaterThanOrEqual(2);
    }
  });

  it("a control that cannot be answered says 3 of 5, names what to connect, and is marked short", () => {
    const { container } = render(<IndexView controls={controls} properties={properties} selection={DEFAULT} />);
    const rate = card(container, "rate_room_category_consistency");
    const lines = [...rate.querySelectorAll("p.readiness")];
    expect(lines).toHaveLength(2);
    for (const line of lines) {
      expect(textOf(line)).toContain("3 of 5 fields");
      expect(textOf(line)).toContain("rate_plan.permitted_room_types");
      expect(line.classList.contains("short")).toBe(true);
    }
    const ready = card(container, "checkout_money_owed").querySelectorAll("p.readiness.short");
    expect(ready).toHaveLength(0);
  });
});

describe("the evidence picker", () => {
  it("offers every property and every capture, and announces exactly the current one", () => {
    const selection = { property: "sandbox", evidence: "sandbox2024" };
    render(<IndexView controls={controls} properties={properties} selection={selection} />);
    const picker = screen.getByRole("navigation", { name: "Bodies of evidence" });
    const links = within(picker).getAllByRole("link");
    const offered = links.map((a) => a.getAttribute("href"));
    expect(offered).toEqual(
      properties.properties.flatMap((p) => p.captures.map((c) => `/?property=${p.id}&evidence=${c}`)),
    );
    const current = links.filter((a) => a.getAttribute("aria-current") === "page");
    expect(current.map((a) => a.getAttribute("href"))).toEqual(["/?property=sandbox&evidence=sandbox2024"]);
  });

  it("every control links to its run page carrying the selected property and evidence", () => {
    const selection = { property: "demo", evidence: "demo2024" };
    const { container } = render(<IndexView controls={controls} properties={properties} selection={selection} />);
    for (const control of controls) {
      const link = card(container, control.control_id).querySelector("a")!;
      expect(link.getAttribute("href")).toBe(`/run/${control.control_id}?property=demo&evidence=demo2024`);
    }
  });

  it("each property names its provider - as data, never as a branch", () => {
    render(<IndexView controls={controls} properties={properties} selection={DEFAULT} />);
    const picker = textOf(screen.getByRole("navigation", { name: "Bodies of evidence" }));
    for (const property of properties.properties) {
      expect(picker).toContain(property.name);
      expect(picker).toContain(property.provider);
    }
  });
});

describe("the selection never trusts the URL", () => {
  it("nothing asked for is the engine's stated default", () => {
    expect(selectionFrom({}, properties)).toEqual(properties.default);
  });

  it("a valid pair is kept", () => {
    expect(selectionFrom({ property: "sandbox", evidence: "sandbox2024" }, properties)).toEqual({
      property: "sandbox",
      evidence: "sandbox2024",
    });
  });

  it("an unknown property falls back to the default property, as the engine does", () => {
    expect(selectionFrom({ property: "../etc", evidence: "sandbox2024" }, properties)).toEqual(properties.default);
  });

  it("a capture of a DIFFERENT property falls back to this property's default capture", () => {
    const sandbox = properties.properties.find((p) => p.id === "sandbox")!;
    expect(selectionFrom({ property: "sandbox", evidence: "demo2024" }, properties)).toEqual({
      property: "sandbox",
      evidence: sandbox.default_capture,
    });
  });

  it("a repeated query parameter is read as its first value, not as a list", () => {
    expect(selectionFrom({ property: ["sandbox", "demo"], evidence: ["sandbox2024"] }, properties)).toEqual({
      property: "sandbox",
      evidence: "sandbox2024",
    });
  });
});

describe("drafts are runnable, unreviewed, and kept apart", () => {
  const draft: ControlEntry = { ...controls[0], control_id: "my_draft", name: "My Draft", reviewed: false };

  it("no drafts section at all when there are none", () => {
    const { container } = render(<IndexView controls={controls} properties={properties} selection={DEFAULT} drafts={[]} />);
    expect(container.querySelector("[data-drafts]")).toBeNull();
  });

  it("a draft is badged, says it is not counted, and never joins the reviewed list", () => {
    const { container } = render(
      <IndexView controls={controls} properties={properties} selection={DEFAULT} drafts={[draft]} />,
    );
    const reviewed = container.querySelector("[data-reviewed]")!;
    expect(reviewed.querySelectorAll("[data-control-id]")).toHaveLength(controls.length);
    expect(reviewed.querySelector('[data-control-id="my_draft"]')).toBeNull();
    const drafts = container.querySelector<HTMLElement>("[data-drafts]")!;
    const text = textOf(drafts.querySelector('[data-control-id="my_draft"]')!);
    expect(text).toContain("draft · unreviewed");
    expect(text).toContain("not counted in the criterion-1 figure");
  });
});

describe("the page explains itself, inline", () => {
  it("names readiness, a body of evidence, and drafts in visible text, never in a title attribute", () => {
    const { container } = render(<IndexView controls={controls} properties={properties} selection={DEFAULT} />);
    const text = textOf(container);
    expect(text).toContain("Readiness");
    expect(text).toContain("body of evidence");
    expect(container.querySelectorAll("[title]")).toHaveLength(0);
  });
});

describe("the ask form preselects what the index chose", () => {
  it("the selected property is checked and its capture is selected", () => {
    const control = controls.find((c) => c.control_id === "checkout_unrefunded_credit")!;
    const { container } = render(
      <AskForm control={control} properties={properties} selection={{ property: "sandbox", evidence: "sandbox2024" }} />,
    );
    const checked = container.querySelector<HTMLInputElement>('input[name="property"]:checked')!;
    expect(checked.value).toBe("sandbox");
    const select = container.querySelector<HTMLSelectElement>('select[name="evidence:sandbox"]')!;
    expect(select.value).toBe("sandbox2024");
    expect(container.querySelector<HTMLInputElement>('input[name="control_id"]')!.value).toBe(control.control_id);
  });

  it("a draft's ask form says it is unreviewed", () => {
    const draft = { ...controls[0], control_id: "my_draft", reviewed: false };
    const { container } = render(<AskForm control={draft} properties={properties} selection={DEFAULT} />);
    expect(textOf(container)).toContain("draft · unreviewed");
  });
});

describe("the not-found page", () => {
  it("states the absence, offers the way back, and carries no inline style our CSP would refuse", async () => {
    const { default: NotFound } = await import("@/app/not-found");
    const { container } = render(<NotFound />);
    expect(textOf(container)).toContain("There is nothing here.");
    expect(container.querySelector('a[href="/"]')).not.toBeNull();
    expect(container.querySelectorAll("[style]")).toHaveLength(0);
  });
});
