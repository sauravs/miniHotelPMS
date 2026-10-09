/**
 * THE PARITY HARNESS - the "nothing breaks" proof, over the WHOLE matrix.
 *
 * A grouping UI can lie in three ways: drop a record, duplicate one, or file it under the wrong
 * answer. For every golden payload - every control, property and capture, live and stored:
 *
 *   rendered (record_id, outcome) pairs, as a multiset  ==  the payload's
 *   number of verdict blocks rendered                   ==  len(verdicts)
 *   within each group, the population order is kept
 *   tiles rendered                                     <=>  coverage.concluded
 *   every evidence line is in its own block: field, value VERBATIM, provenance   (criterion 3)
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { RunView } from "@/components/RunView";
import type { RunPayload } from "@/lib/types";
import { liveRuns, outcomes, run, stored, storedRuns } from "./goldens";

afterEach(cleanup);

const pairs = (items: [string, string][]) => items.map(([r, o]) => `${o}:${r}`).sort();

function assertParity(payload: RunPayload) {
  const { container } = render(<RunView run={payload} outcomes={outcomes} />);
  const blocks = [...container.querySelectorAll("article.verdict")];

  expect(blocks).toHaveLength(payload.verdicts.length);
  expect(pairs(blocks.map((b) => [b.getAttribute("data-record-id")!, b.getAttribute("data-outcome")!]))).toEqual(
    pairs(payload.verdicts.map((v) => [v.record_id ?? "", v.outcome])),
  );
  for (const outcome of outcomes.group_order) {
    const group = container.querySelector(`#verdicts-${outcome}`);
    const rendered = group
      ? [...group.querySelectorAll("article.verdict")].map((b) => b.getAttribute("data-record-id"))
      : [];
    expect(rendered).toEqual(payload.verdicts.filter((v) => v.outcome === outcome).map((v) => v.record_id ?? ""));
    const members = payload.verdicts.filter((v) => v.outcome === outcome);
    [...(group?.querySelectorAll("article.verdict") ?? [])].forEach((block, index) => {
      expect(block.getAttribute("data-outcome")).toBe(outcome);
      const rows = [...block.querySelectorAll("table.evidence tbody tr")].map((tr) =>
        [...tr.querySelectorAll("td")].map((td) => td.textContent),
      );
      expect(rows).toEqual(
        members[index].evidence.map((line) => [
          line.field,
          line.known ? line.value : expect.stringContaining(line.reason ?? ""),
          line.source ?? "—",
        ]),
      );
    });
  }
  const hasTiles = container.querySelector("ul.tiles") !== null;
  expect(hasTiles).toBe(payload.coverage.concluded);
}

describe("parity over every live run in the matrix", () => {
  it("there is a matrix to check", () => expect(liveRuns.length).toBeGreaterThanOrEqual(44));
  it.each(liveRuns)("%s", (name) => assertParity(run(name)));
});

describe("parity over every stored run - what the run page actually renders", () => {
  it("there is a matrix to check", () => expect(storedRuns.length).toBe(liveRuns.length));
  it.each(storedRuns)("%s", (name) => assertParity(stored(name)));
});
