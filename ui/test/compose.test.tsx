/**
 * The compose window on the second surface. Decision D10, made visible and structural:
 *
 *   - a model drafts a sentence; the deterministic grammar decides; a PERSON files it. The
 *     sentence arrives in an editable box, and what is filed is whatever is in the box.
 *   - a question is an answer, not an error, and offers nothing to file.
 *   - a refusal names what is missing in the validator's own words, and offers nothing to file.
 *   - switched off is STATED, with how to switch it on - never a blank page or a 404.
 *
 * Rendered from the golden payloads of a real conversation with the stub proposer.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ComposeView } from "@/components/ComposeView";
import { IndexView, selectionFrom } from "@/components/IndexView";
import type { AcceptRefused, ComposeState, ComposeTurnResponse, ControlEntry, Properties } from "@/lib/types";
import { golden } from "./goldens";

afterEach(cleanup);

const textOf = (element: Element) => (element.textContent ?? "").replace(/\s+/g, " ").trim();
const properties = golden<Properties>("properties.json");
const selection = selectionFrom({}, properties);
const off = golden<ComposeState>("compose/off.json");
const wired = golden<ComposeState>("compose/wired.json");
const turn = (name: string) => golden<ComposeTurnResponse>(`compose/${name}.json`);

const view = (extra: Partial<Parameters<typeof ComposeView>[0]> = {}) =>
  render(<ComposeView state={wired} properties={properties} selection={selection} {...extra} />).container;

const fileForm = (container: HTMLElement) => container.querySelector("form[data-file]");

describe("switched off is stated, not hidden", () => {
  it("says so, says why, and gives the commands - with no form to fill in", () => {
    const { container } = render(<ComposeView state={off} properties={properties} selection={selection} />);
    const text = textOf(container);
    expect(text).toContain("No proposer is wired");
    expect(text).toContain("--llm stub");
    expect(container.querySelector("form")).toBeNull();
  });
});

describe("before anything is asked", () => {
  it("names the proposer, offers every reviewed control's population, and nothing to file", () => {
    const container = view();
    expect(textOf(container)).toContain(wired.proposer!);
    const options = [...container.querySelectorAll<HTMLOptionElement>('form[data-ask] select[name="template"] option')];
    expect(options.map((o) => o.value)).toEqual(wired.templates.map((t) => t.control_id));
    expect(options.find((o) => o.selected)?.value).toBe(wired.template);
    expect(fileForm(container)).toBeNull();
  });
});

describe("a sentence that compiles", () => {
  const compiles = turn("compiles");

  it("says it compiles, lists the fields it reads, and puts the sentence in an EDITABLE box", () => {
    const container = view({ response: compiles });
    const card = container.querySelector("[data-result]")!;
    expect(card.classList.contains("PASS")).toBe(true);
    expect(textOf(card)).toContain("THIS COMPILES");
    for (const field of compiles.result.fields) expect(textOf(card)).toContain(field);
    // The box is in the form that FILES it: what is in the box is what is filed.
    const box = fileForm(container)!.querySelector<HTMLTextAreaElement>('textarea[name="sentence"]')!;
    expect(box.value).toBe(compiles.result.sentence);
    expect(box.readOnly).toBe(false);
    expect(textOf(card)).toContain("What runs is what is in the box");
  });

  it("the file form carries the conversation, a name, an id, a population and where to run it", () => {
    const form = fileForm(view({ response: compiles }))!;
    for (const name of ["sentence", "control_id", "name", "template", "property", "conversation"]) {
      expect(form.querySelector(`[name="${name}"]`), name).not.toBeNull();
    }
    expect(form.querySelector<HTMLInputElement>('[name="conversation"]')!.value).toBe(compiles.conversation);
    expect(textOf(form)).toContain("File as draft and run it");
  });
});

describe("a refusal and a question offer nothing to file", () => {
  it("a refusal names the missing vocabulary in the validator's words", () => {
    const refused = turn("refused");
    const container = view({ response: refused });
    const card = container.querySelector("[data-result]")!;
    expect(card.classList.contains("FAIL")).toBe(true);
    expect(textOf(card)).toContain("REFUSED");
    for (const problem of refused.result.problems) expect(textOf(card)).toContain(problem);
    expect(textOf(card)).toContain("room.inspection_status");
    expect(fileForm(container)).toBeNull();
  });

  it("a question is a question, not an error - and is the better answer than an invented rule", () => {
    const question = turn("question");
    const container = view({ response: question });
    const card = container.querySelector("[data-result]")!;
    expect(card.classList.contains("UNKNOWN")).toBe(true);
    expect(textOf(card)).toContain("A QUESTION, NOT A RULE");
    expect(textOf(card)).toContain(question.result.question);
    expect(textOf(card)).not.toContain("REFUSED");
    expect(fileForm(container)).toBeNull();
  });
});

describe("the conversation", () => {
  it("shows every turn in order, with each refusal's reasons and each question", () => {
    const compiles = turn("compiles");
    const container = view({ response: compiles });
    const turns = [...container.querySelectorAll("[data-turn]")];
    expect(turns.map((t) => t.querySelector(".says")!.textContent)).toEqual(
      compiles.transcript.map((t) => `you ${t.prose}`),
    );
    compiles.transcript.forEach((t, index) => {
      for (const problem of t.problems) expect(textOf(turns[index])).toContain(problem);
      if (t.question) expect(textOf(turns[index])).toContain(t.question);
    });
  });

  it("the next question carries the conversation forward", () => {
    const compiles = turn("compiles");
    const ask = view({ response: compiles }).querySelector("form[data-ask]")!;
    expect(ask.querySelector<HTMLInputElement>('[name="conversation"]')!.value).toBe(compiles.conversation);
  });
});

describe("filing a sentence the grammar refuses", () => {
  it("shows the sentence and the reasons, writes nothing, and offers the box back to edit", () => {
    const refusal = golden<AcceptRefused>("compose/accept-refused.json");
    const container = view({ response: turn("compiles"), refusal });
    const card = container.querySelector("[data-refusal]")!;
    expect(textOf(card)).toContain("REFUSED");
    expect(textOf(card)).toContain(refusal.sentence);
    for (const problem of refusal.problems) expect(textOf(card)).toContain(problem);
    expect(fileForm(container)!.querySelector<HTMLTextAreaElement>('textarea[name="sentence"]')!.value).toBe(
      refusal.sentence,
    );
  });
});

describe("the page explains itself, inline", () => {
  it("says a draft is unreviewed and uncounted, and that a model never decides - not in a title attribute", () => {
    const container = view();
    const text = textOf(container);
    expect(text).toContain("not counted");
    expect(text).toContain("never decides");
    expect(container.querySelectorAll("[title]")).toHaveLength(0);
  });
});

describe("the index offers compose only when it is wired", () => {
  const { controls } = golden<{ controls: ControlEntry[] }>("controls.json");
  it("absent when off, a link naming the proposer when on", () => {
    const offIndex = render(<IndexView controls={controls} properties={properties} selection={selection} />).container;
    expect(offIndex.querySelector('a[href="/compose"]')).toBeNull();
    cleanup();
    const onIndex = render(
      <IndexView controls={controls} properties={properties} selection={selection} compose="stub" />,
    ).container;
    expect(onIndex.querySelector('a[href="/compose"]')).not.toBeNull();
    expect(textOf(onIndex)).toContain("stub");
  });
});
