/**
 * One run: what was asked, what it cost, and every answer with its evidence.
 *
 * THE ORDER OF THE THREE STATES BELOW IS THE MOST IMPORTANT THING IN THIS FILE.
 *
 *   blocked             the run never happened. No counts exist, and none are shown.
 *   not concluded       the run looked and decided nothing. `counts` IS in the payload - four
 *                       numbers, a zero under VIOLATION - and showing them would read as a clean
 *                       bill of health for a control that never looked (finding F5, criterion 8).
 *   concluded           only now are there tiles.
 *
 * The gate is `coverage.concluded`. Never `counts !== undefined`: that is trap 1, and it is the
 * mistake v1 shipped.
 */
import type { Counts, Outcomes, OutcomeWording, ReadinessReport, RunPayload } from "@/lib/types";
import { Verdict } from "./Verdict";

export function RunView({
  run,
  outcomes,
  readiness = run.readiness,
}: {
  run: RunPayload;
  outcomes: Outcomes;
  readiness?: ReadinessReport[];
}) {
  const wording = byOutcome(outcomes);
  return (
    <>
      <div className="card">
        <p className="sentence">{run.natural_language}</p>
        <p className="meta">
          <strong>{run.control_name}</strong> · <code>{run.control_id}</code>
        </p>
        <p className="meta">
          Property <strong>{run.tenant_id}</strong> · provider <strong>{run.provider}</strong> ·
          evidence <strong>{run.evidence.label}</strong>
          {run.evidence.synthetic ? " (synthetic)" : ""} · asked as of <strong>{run.as_of}</strong>{" "}
          · {run.calls} provider call(s)
        </p>
        <p className={`meta ${run.freshness.stale ? "stale" : ""}`}>{run.freshness.headline}</p>
        {run.execution ? <p className="meta">{run.execution.headline}</p> : null}
        {readiness.map((report) => (
          <p key={report.provider} className={`readiness${report.executable ? "" : " short"}`}>
            {report.headline}
          </p>
        ))}
        <p className="meta">
          Run <code>{run.run_id}</code> ·{" "}
          <a href={`/history/${encodeURIComponent(run.control_id)}`}>every run of this control</a>
        </p>
      </div>

      {run.blocked !== null ? (
        <div className="blocked">
          <p>
            <strong>This control could not run against this body of evidence.</strong>
          </p>
          <p>{run.blocked}</p>
          <WhyNoCounts blocked />
        </div>
      ) : run.coverage.concluded && run.counts ? (
        <>
          <Tiles counts={run.counts} outcomes={outcomes} />
          <p className="meta">{run.coverage.headline}</p>
        </>
      ) : (
        <div className="no-conclusion">
          <p>
            <strong>{run.coverage.headline}</strong>
          </p>
          <Reasons reasons={run.coverage.reasons} />
          <WhyNoCounts blocked={false} />
        </div>
      )}

      {run.verdicts.length > 0 ? (
        <>
          <Glossary outcomes={outcomes} />
          <h2>
            Answers, record by record{" "}
            <span className="count">
              {run.verdicts.length} record{run.verdicts.length === 1 ? "" : "s"}
            </span>
          </h2>
          <VerdictGroups run={run} outcomes={outcomes} wording={wording} />
        </>
      ) : null}
    </>
  );
}

function byOutcome(outcomes: Outcomes): Record<string, OutcomeWording> {
  return Object.fromEntries(outcomes.outcomes.map((entry) => [entry.outcome, entry]));
}

/**
 * The scoreboard, which is also the page's table of contents. A tile with records behind it
 * links to them; a zero is stated but is not a link to a section that does not exist.
 * EXCLUDED has its own tile and is never folded into PASS.
 */
export function Tiles({ counts, outcomes }: { counts: Counts; outcomes: Outcomes }) {
  return (
    <ul className="tiles" aria-label="How many records reached each answer">
      {outcomes.outcomes.map(({ outcome, badge }) => {
        const count = counts[outcome];
        const inner = (
          <>
            <span className="n">{count}</span>
            <span className="k">{badge}</span>
          </>
        );
        return (
          <li key={outcome} className={outcome}>
            {count ? <a href={`#verdicts-${outcome}`}>{inner}</a> : <span className="box">{inner}</span>}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Every verdict, grouped by its answer in work-queue order - violations, then gaps, then
 * passes, then records the control never applied to. Within a group the population order is
 * KEPT: the order the evidence arrived in is itself evidence, so this regroups and never sorts.
 * A collapsed group is still in the document - collapsing is not omitting.
 */
function VerdictGroups({
  run,
  outcomes,
  wording,
}: {
  run: RunPayload;
  outcomes: Outcomes;
  wording: Record<string, OutcomeWording>;
}) {
  return (
    <>
      {outcomes.group_order.map((outcome) => {
        const members = run.verdicts.filter((verdict) => verdict.outcome === outcome);
        if (members.length === 0) return null;
        const words = wording[outcome];
        return (
          <details key={outcome} className={`group ${outcome}`} id={`verdicts-${outcome}`} open={words.open}>
            <summary>
              <span className={`chip ${outcome}`}>{words.badge}</span>
              <strong className="tally">
                {members.length} record{members.length === 1 ? "" : "s"}
              </strong>
              <span className="gist">{words.group_meaning}</span>
            </summary>
            <div className="group-body">
              {members.map((verdict, index) => (
                <Verdict key={index} verdict={verdict} wording={words} />
              ))}
            </div>
          </details>
        );
      })}
    </>
  );
}

/** The four answers and what each means, built from the engine's wording - never restated. */
export function Glossary({ outcomes }: { outcomes: Outcomes }) {
  return (
    <details className="glossary">
      <summary>What the four answers mean</summary>
      <dl>
        {outcomes.outcomes.map(({ outcome, badge, means }) => (
          <div key={outcome}>
            <dt>
              <span className={`chip ${outcome}`}>{badge}</span>
            </dt>
            <dd>{means}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function Reasons({ reasons }: { reasons: RunPayload["coverage"]["reasons"] }) {
  if (reasons.length === 0) return null;
  return (
    <div className="scroller">
      <table className="listing">
        <caption>Why this run concluded nothing, by number of records</caption>
        <thead>
          <tr>
            <th scope="col">records</th>
            <th scope="col">reason</th>
          </tr>
        </thead>
        <tbody>
          {reasons.map(({ reason, records }, index) => (
            <tr key={index}>
              <td>{records}</td>
              <td>{reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Why the tile row is absent, said where its absence is visible. Two absences, two sentences:
 * "we looked and could not tell" against "we could not look" is UNKNOWN against FAIL, one
 * level up.
 */
function WhyNoCounts({ blocked }: { blocked: boolean }) {
  return (
    <details className="aside">
      <summary>Why are there no counts?</summary>
      <p>
        Deliberately. <strong>No counts are shown</strong> for{" "}
        {blocked ? (
          <>
            a run that <strong>never ran</strong>: the evidence it needs was not in this body of
            responses, so there was nothing to reach a conclusion about
          </>
        ) : (
          <>
            a run that looked at records and <strong>could not decide about a single one</strong>
          </>
        )}
        , because four zeroes - one of them under VIOLATION - read as a clean bill of health. This
        control has not found the property compliant, and the reason is above.
      </p>
    </details>
  );
}
