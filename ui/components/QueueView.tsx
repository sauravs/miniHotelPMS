/**
 * One property's findings queue (slice 18): what is still to do, what was closed, and - beside it
 * - what each control last concluded.
 *
 * AN EMPTY QUEUE IS NOT AN ALL-CLEAR. A task is raised only by a VIOLATION, only by a reviewed
 * control, and only from a run made against the engine's store. NO ANSWER raises none (open
 * question 1.1), and nor does a run that concluded nothing or could not run. So the coverage
 * table is not decoration: it is the only thing on this page that can tell "nothing is wrong"
 * from "nothing has looked" - criterion 8, applied to a new surface.
 *
 * Every word that means something comes from the engine: the VIOLATION badge from
 * `/api/outcomes`, each control's status `label` and `headline`, the persistence sentence, and
 * the task's own `reason`, whose money carries its currency and is never parsed (R9).
 *
 * The two moves are two forms posting to a Server Action, so a task changes state only when a
 * person presses a button. Plain `<a>` for links, as everywhere else in this UI.
 */
import type { ActionRecord, Outcomes, Properties, Queue, QueueControl } from "@/lib/types";
import { Explainer } from "./Explainer";
import { Policy } from "./Policy";

type Move = (formData: FormData) => Promise<void>;

export function QueueView({
  queue,
  properties,
  outcomes,
  action,
}: {
  queue: Queue;
  properties: Properties;
  outcomes: Outcomes;
  action?: Move;
}) {
  const pending = queue.records.filter((record) => record.state === "pending");
  const closed = queue.records.filter((record) => record.state !== "pending");
  const violation = outcomes.outcomes.find((o) => o.outcome === "FAIL")!.badge;
  return (
    <>
      <Explainer lede="Every VIOLATION a reviewed control found becomes one task here. A person marks it done or dismisses it; running the control again never adds it twice.">
        <p>
          <strong>Only a VIOLATION raises a task.</strong> NO ANSWER does not: whether records
          nobody could check should become a review queue is an open question for the hotel, and
          this page does not answer it by accident. Nor does a run that concluded nothing or could
          not run at all.
        </p>
        <p>
          <strong>One task per record, per rule.</strong> Re-running a control finds the same task.
          A new version of the rule judges afresh, and the old task stays linked to the version
          that raised it.
        </p>
        <p>
          <strong>A run never closes a task.</strong> If a later run finds the record passing, the
          task says so and stays pending: the evidence only says the problem stopped showing, not
          that anybody dealt with it.
        </p>
        <p>
          <strong>An empty queue is not an all-clear.</strong> The table at the bottom says what
          each control&apos;s latest run concluded.
        </p>
      </Explainer>

      <div className="card">
        <p className="sentence">
          Findings queue · property <strong>{queue.property}</strong>
        </p>
        <nav className="evidence-picker" aria-label="Properties">
          {properties.properties.map((property) => {
            const current = property.id === queue.property;
            return (
              <a
                key={property.id}
                className={current ? "current" : ""}
                aria-current={current ? "page" : undefined}
                href={`/queue?property=${encodeURIComponent(property.id)}`}
              >
                {property.id}
              </a>
            );
          })}
        </nav>
        <p className={queue.persistent ? "meta" : "meta stale"} data-persistence="">
          {queue.persistence}
        </p>
        {/* Slice 19. "Nobody was emailed" and "email is not wired" are different facts, and a
            reader of a task with no delivery line needs to know which one is true. */}
        <p className="meta" data-email="">
          {queue.email?.wired
            ? `Email is wired (${queue.email.via}): each new task is emailed once to its audience's route.`
            : "Email is not wired on this engine, so nobody is emailed about a task."}
        </p>
      </div>

      <h2>
        To do{" "}
        <span className="count">
          {pending.length} task{pending.length === 1 ? "" : "s"}
        </span>
      </h2>
      {pending.length === 0 ? (
        <div className="no-conclusion" data-empty="">
          <p>
            <strong>Nothing is waiting in this queue - and that is not an all-clear.</strong>
          </p>
          <p>
            A task is raised only by a VIOLATION, only by a reviewed control, and only from a run made
            against the engine&apos;s store. NO ANSWER raises none. The table below says, control by
            control, whether its latest run reached a conclusion at all.
          </p>
        </div>
      ) : (
        pending.map((record) => (
          <Task key={record.action_id} record={record} badge={violation} action={action} />
        ))
      )}

      {closed.length > 0 ? (
        <details className="group EXCLUDED" data-closed="">
          <summary>
            <strong className="tally">
              {closed.length} closed task{closed.length === 1 ? "" : "s"}
            </strong>
            <span className="gist">Marked done or dismissed by a person. A run never closes a task.</span>
          </summary>
          <div className="group-body">
            {closed.map((record) => (
              <Task key={record.action_id} record={record} badge={violation} action={action} />
            ))}
          </div>
        </details>
      ) : null}

      <h2>What each control last concluded</h2>
      <div className="card">
        <div className="scroller">
          <table className="listing">
            <caption>
              Each reviewed control&apos;s latest run against the engine&apos;s store. Only a run that
              concluded something can raise a task; the others have not looked.
            </caption>
            <thead>
              <tr>
                <th scope="col">control</th>
                <th scope="col">severity · audience</th>
                <th scope="col">latest run</th>
                <th scope="col">what it says</th>
                <th scope="col">pending</th>
              </tr>
            </thead>
            <tbody>
              {queue.controls.map((control) => (
                <ControlRow key={control.control_id} control={control} property={queue.property} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

const stored = (runId: string, property: string) =>
  `/runs/${encodeURIComponent(runId)}?property=${encodeURIComponent(property)}`;

function Task({ record, badge, action }: { record: ActionRecord; badge: string; action?: Move }) {
  return (
    <article className="verdict FAIL task" data-action-id={record.action_id} data-state={record.state}>
      <span className="badge">{badge}</span>
      <span className="record">{record.record_id}</span>
      <p className="says">{record.reason}</p>
      <p className="meta">
        <strong>{record.control_name}</strong> · <code>{record.control_id}</code> · severity{" "}
        <strong>{record.severity}</strong> · for <strong>{record.audience ?? "no audience declared"}</strong>
      </p>
      <p className="meta">
        Raised by run{" "}
        <a className="mono" href={stored(record.raised.run_id, record.property)}>
          {record.raised.run_id}
        </a>
        , asked as of {record.raised.as_of}, over {record.raised.evidence} · last found failing by run{" "}
        <span className="mono">{record.last_failing.run_id}</span>
      </p>
      <p className="meta policy">
        <Policy version={record.policy_version} digest={record.policy_digest} />
      </p>
      {record.annotation ? <p className="means">{record.annotation}</p> : null}
      <Delivery record={record} />
      {record.state === "pending" ? (
        <div className="moves">
          {(
            [
              ["done", "Mark done"],
              ["dismissed", "Dismiss"],
            ] as const
          ).map(([state, label]) => (
            <form key={state} action={action}>
              <input type="hidden" name="action_id" value={record.action_id} />
              <input type="hidden" name="property" value={record.property} />
              <input type="hidden" name="state" value={state} />
              <button type="submit">{label}</button>
            </form>
          ))}
        </div>
      ) : (
        <p className="meta">
          <strong>{record.state === "done" ? "Marked done" : "Dismissed"}</strong> by {record.state_changed_by} at{" "}
          {record.state_changed_at}
        </p>
      )}
    </article>
  );
}

/** What happened to a task's email (slice 19), or nothing when there is nothing to say. */
function Delivery({ record }: { record: ActionRecord }) {
  const delivery = record.delivery;
  if (!delivery) return null;
  if (delivery.sent_at) {
    return (
      <p className="meta delivery">
        Emailed to {record.audience ?? "its audience"} at {delivery.sent_at}.
      </p>
    );
  }
  if (delivery.note) return <p className="meta delivery">Not emailed: {delivery.note}.</p>;
  return null;
}

function ControlRow({ control, property }: { control: QueueControl; property: string }) {
  const latest = control.latest_run;
  return (
    <tr data-control-id={control.control_id} data-status={control.status}>
      <td>
        <a href={`/history/${encodeURIComponent(control.control_id)}?property=${encodeURIComponent(property)}`}>
          {control.name}
        </a>
        <br />
        <code>{control.control_id}</code>
      </td>
      <td>
        {control.severity} · {control.audience ?? "no audience declared"}
      </td>
      <td>
        {latest === null ? (
          "—"
        ) : (
          <>
            <a className="mono" href={stored(latest.run_id, property)}>
              {latest.run_id}
            </a>
            <br />
            <span className="meta">
              {latest.evidence_label} · as of {latest.as_of}
            </span>
          </>
        )}
      </td>
      <td>
        <strong>{control.label}</strong> · {control.headline}
      </td>
      <td>{control.pending}</td>
    </tr>
  );
}
