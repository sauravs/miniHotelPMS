/**
 * Every control the spec defines, with what each PMS could answer about it - criterion 10.
 *
 * Readiness lines are the engine's own sentences ("3 of 5 fields available - connect a source
 * for ..."), rendered as they arrive. A line that is short is MARKED short, because a control
 * that cannot be answered yet is the one place this page has something to sell: until the named
 * source is connected, the control answers NO ANSWER rather than guessing.
 *
 * Plain `<a>`, not `next/link`: a link that works with no script is the engine surface's habit
 * and worth keeping, it keeps this component renderable outside Next (the e2e layer does exactly
 * that), and it means no route is ever prefetched behind the reader's back.
 */
import type { ControlEntry, Properties } from "@/lib/types";
import { Explainer } from "./Explainer";

export interface Selection {
  property: string;
  evidence: string;
}

type Query = Record<string, string | string[] | undefined>;

const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);

/**
 * Which property and which body of evidence a request is about - never trusted from the URL.
 *
 * The engine's own rule (`App._selection`): a property nobody configured falls back to the
 * default property, and a capture this property's provider cannot replay falls back to its
 * default capture. A mistyped query string is not worth a refusal, and the page always shows
 * which selection it actually used.
 */
export function selectionFrom(query: Query, properties: Properties): Selection {
  const property =
    properties.properties.find((p) => p.id === first(query.property)) ??
    properties.properties.find((p) => p.id === properties.default.property)!;
  const asked = first(query.evidence);
  const evidence = asked && property.captures.includes(asked) ? asked : property.default_capture;
  return { property: property.id, evidence };
}

const runHref = (controlId: string, { property, evidence }: Selection) =>
  `/run/${encodeURIComponent(controlId)}?property=${encodeURIComponent(property)}&evidence=${encodeURIComponent(evidence)}`;

export function IndexView({
  controls,
  properties,
  selection,
  drafts = [],
  compose = null,
}: {
  controls: ControlEntry[];
  properties: Properties;
  selection: Selection;
  drafts?: ControlEntry[];
  /** The wired proposer's name, or null. Compose is offered only when it can actually answer. */
  compose?: string | null;
}) {
  return (
    <>
      <Explainer lede="Each card below is one governance rule. Pick one to run it against a body of captured evidence and see the fields behind every answer.">
        <p>
          <strong>The sentence</strong> at the top of a card is the rule itself, not a description
          of it. It compiles to something that runs.
        </p>
        <p>
          <strong>Readiness</strong> - <code>5 of 5 fields available</code> - counts the fields the
          rule needs against the fields each system can actually supply, reported for each system
          separately. When it is short the line names what to <em>connect a source</em> for, and
          until that is connected the control answers NO ANSWER rather than guessing.
        </p>
        <p>
          <strong>A body of evidence</strong> is a frozen set of real responses, captured once from a
          live system and pseudonymised. A run replays it, so the same question always gets the
          same answer and nothing here touches a live system.
        </p>
        <p>
          <strong>A draft</strong> is a rule composed from prose and filed but not reviewed. It is
          runnable, badged everywhere it appears, and not counted in the figure that reports how
          many controls reach an answer.
        </p>
      </Explainer>

      <h2>Bodies of evidence</h2>
      <nav className="card" aria-label="Bodies of evidence">
        {properties.properties.map((property) => (
          <div key={property.id}>
            <p className="meta">
              <strong>{property.name}</strong> · {property.provider}
            </p>
            <p className="evidence-picker">
              {property.captures.map((capture) => {
                const current = property.id === selection.property && capture === selection.evidence;
                return (
                  <a
                    key={capture}
                    className={current ? "current" : ""}
                    aria-current={current ? "page" : undefined}
                    href={`/?property=${encodeURIComponent(property.id)}&evidence=${encodeURIComponent(capture)}`}
                  >
                    {capture}
                  </a>
                );
              })}
            </p>
          </div>
        ))}
        <p className="meta">
          A run is asked about the instant its evidence describes. Asking a capture about a window
          it never covered is refused rather than answered with an empty population.
        </p>
      </nav>

      {/* The findings queue (slice 18), for the selected property. A free read of the engine's
          store; an empty queue explains itself rather than reading as an all-clear. */}
      <div className="card">
        <p className="sentence">
          <a href={`/queue?property=${encodeURIComponent(selection.property)}`}>Findings queue</a>
        </p>
        <p className="meta">
          Every VIOLATION a reviewed control found, as a task a person marks done or dismisses -
          beside what each control last concluded, because an empty queue is not an all-clear.
        </p>
      </div>

      {compose ? (
        <div className="card">
          <p className="sentence">
            <a href="/compose">Compose a control from prose</a>
          </p>
          <p className="meta">
            Describe a rule in your own words and the <strong>{compose}</strong> proposer rewrites it
            as a restricted sentence, which the same grammar and validator then turn into a rule.
            Composed rules are filed as drafts.
          </p>
        </div>
      ) : null}

      <h2>Controls</h2>
      <div data-reviewed="">
        {controls.map((control) => (
          <ControlCard key={control.control_id} control={control} selection={selection} />
        ))}
      </div>

      {/* Drafts last and visibly apart. Mixing them in with the reviewed controls would blur the
          line the criterion-1 figure depends on. */}
      {drafts.length > 0 ? (
        <div data-drafts="">
          <h2>Drafts</h2>
          {drafts.map((draft) => (
            <ControlCard key={draft.control_id} control={draft} selection={selection} />
          ))}
        </div>
      ) : null}
    </>
  );
}

function ControlCard({ control, selection }: { control: ControlEntry; selection: Selection }) {
  return (
    <div className="card" data-control-id={control.control_id}>
      <p className="sentence">
        <a href={runHref(control.control_id, selection)}>{control.name}</a>
        {control.reviewed ? null : (
          <>
            {" "}
            <span className="draft-badge">draft · unreviewed</span>
          </>
        )}
      </p>
      <p className="meta">{control.natural_language}</p>
      <p className="meta">
        <code>{control.control_id}</code> · one record is one {control.entity}
        {control.reviewed ? null : " · not counted in the criterion-1 figure"} ·{" "}
        <a href={`/history/${encodeURIComponent(control.control_id)}?property=${encodeURIComponent(selection.property)}`}>
          history
        </a>
      </p>
      {control.readiness.map((report) => (
        <p key={report.provider} className={`readiness${report.executable ? "" : " short"}`}>
          {report.headline}
        </p>
      ))}
    </div>
  );
}
