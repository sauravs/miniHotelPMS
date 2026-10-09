/**
 * One record's answer, and the evidence that produced it. Criterion 3, literally: every field,
 * its value WITH its unit, the call it came from, and - for a gap - the reason it is a gap.
 *
 * Criterion 2's three signals: the class `verdict <OUTCOME>` carries the hue and the border style
 * (from the engine's own stylesheet, so both surfaces share one set of rules), and the badge and
 * the sentence carry the words. The words are the only signal that survives being read aloud.
 */
import type { EvidenceLine, OutcomeWording, VerdictPayload } from "@/lib/types";

export function Verdict({ verdict, wording }: { verdict: VerdictPayload; wording: OutcomeWording }) {
  return (
    <article
      className={`verdict ${verdict.outcome}`}
      data-outcome={verdict.outcome}
      data-record-id={verdict.record_id ?? ""}
    >
      <span className="badge">{wording.badge}</span>
      <span className="record">{verdict.record_id ?? "(no record id)"}</span>
      <p className="says">{verdict.reason}</p>
      <p className="means">{verdict.means}</p>
      {/* The scroller is around the table, not on it: an UNKNOWN's reason is a whole sentence,
          and a page that scrolls sideways takes the badge off the screen. */}
      <div className="scroller">
        <table className="evidence">
          <caption>Evidence behind this answer</caption>
          <thead>
            <tr>
              <th scope="col">field</th>
              <th scope="col">value</th>
              <th scope="col">from</th>
            </tr>
          </thead>
          <tbody>
            {verdict.evidence.map((line, index) => (
              <EvidenceRow key={index} line={line} />
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function EvidenceRow({ line }: { line: EvidenceLine }) {
  return (
    <tr>
      <td>
        <code>{line.field}</code>
      </td>
      {line.known ? (
        // VERBATIM. "-490.75 ILS" is one value; parsing it keeps the number and loses the
        // currency, and a bare amount invites arithmetic across currencies with no rate (R9).
        <td>{line.value}</td>
      ) : (
        <td className="gap">
          unknown ({line.reason})
          {line.risk ? (
            <>
              {" "}
              <span className="mono">{line.risk}</span>
            </>
          ) : null}
        </td>
      )}
      {/* Opaque provenance: shown as it arrived, never split or branched on. */}
      <td className="from mono">{line.source ?? "—"}</td>
    </tr>
  );
}
