/**
 * Every past run of one control, newest first - what it was asked, what it answered, and what
 * the answer cost.
 *
 * THE OUTCOME CELL HAS THREE STATES, GATED EXACTLY AS A RUN IS (criterion 8, issue #35):
 *
 *   blocked          the reason. No counts exist.
 *   not concluded    the engine's sentence. `counts` IS in the row - and four numbers with a zero
 *                    under VIOLATION for a control that never looked is finding F5.
 *   concluded        the four counts, in tile order, with the engine's badges; EXCLUDED its own.
 *
 * Every run id links to `/runs/<id>`, which re-reads the stored run for free (R1). Re-running a
 * control to answer "what did it say?" is the expensive mistake this page exists to prevent.
 */
import type { ControlEntry, History, HistoryRow, Outcomes } from "@/lib/types";
import { Explainer } from "./Explainer";

export function HistoryView({
  control,
  history,
  outcomes,
}: {
  control: ControlEntry;
  history: History;
  outcomes: Outcomes;
}) {
  const runHref = `/run/${encodeURIComponent(control.control_id)}`;
  return (
    <>
      <Explainer lede="Every run of this control the engine has kept, newest first - what it was asked, what it answered, and what the answer cost.">
        <p>
          <strong>Re-reading a past run costs no provider call.</strong> Some evidence is one call
          per record on somebody else&apos;s server with no bulk endpoint behind it, so re-running a
          control just to answer <em>what did it say?</em> is the expensive mistake this page exists
          to prevent.
        </p>
        <p>
          <strong>As of</strong> is the instant each run asked about, and <strong>evidence</strong>{" "}
          is which capture it replayed. Two runs that disagree usually asked different questions
          rather than got different answers.
        </p>
        <p>
          A run that <strong>reached no conclusion</strong> shows the reason instead of counts:
          four zeroes - one of them under VIOLATION - would read as a clean bill of health for a
          control that never looked.
        </p>
      </Explainer>

      <div className="card">
        <p className="sentence">{control.natural_language}</p>
        <p className="meta">
          <strong>{control.name}</strong> · <code>{control.control_id}</code> ·{" "}
          <a href={runHref}>run it</a>
        </p>
      </div>

      {history.runs.length === 0 ? (
        <div className="card">
          <p>This control has not been run since the engine started.</p>
          <p className="meta">
            <a href={runHref}>Run it</a>
          </p>
        </div>
      ) : (
        <div className="card">
          <div className="scroller">
            <table className="listing">
              <caption>Every run of this control, newest first</caption>
              <thead>
                <tr>
                  <th scope="col">run</th>
                  <th scope="col">made</th>
                  <th scope="col">evidence</th>
                  <th scope="col">as of</th>
                  <th scope="col">calls</th>
                  <th scope="col">outcome</th>
                </tr>
              </thead>
              <tbody>
                {history.runs.map((run) => (
                  <tr key={run.run_id} data-run-id={run.run_id}>
                    <td className="mono">
                      <a href={`/runs/${encodeURIComponent(run.run_id)}`}>{run.run_id}</a>
                    </td>
                    <td>{run.created_at}</td>
                    <td>
                      {run.evidence_label} ({run.provider})
                    </td>
                    <td>{run.as_of}</td>
                    <td>{run.calls}</td>
                    <td>
                      <Outcome run={run} outcomes={outcomes} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="meta">Re-reading any of these costs no provider call (R1).</p>
        </div>
      )}
    </>
  );
}

function Outcome({ run, outcomes }: { run: HistoryRow; outcomes: Outcomes }) {
  if (run.blocked !== null) {
    return (
      <>
        <strong>blocked</strong>: {run.blocked}
      </>
    );
  }
  if (!run.concluded || !run.counts) return <>{run.headline}</>;
  const counts = run.counts;
  return (
    <>
      <span className="counts">
        {outcomes.outcomes.map(({ outcome, badge }) => `${counts[outcome]} ${badge}`).join(" · ")}
      </span>
      <br />
      <span className="meta">{run.headline}</span>
    </>
  );
}
