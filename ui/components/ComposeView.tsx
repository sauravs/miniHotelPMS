/**
 * The compose window: prose in, one restricted sentence out, a draft filed only on request.
 *
 * DECISION D10, MADE STRUCTURAL. A model drafts a sentence; the same deterministic grammar that
 * compiles every hand-written rule decides whether it is one; a person files it. So:
 *
 *   - the sentence arrives in an EDITABLE box, and what is filed is whatever is in the box;
 *   - a question gets no button - a proposer that declined to invent hotel policy has produced no
 *     rule, and offering to file one anyway would undo the restraint worth having;
 *   - a refusal names what is missing in the validator's own words, and gets no button either.
 *
 * Pure: every state renders from a payload, so every state is tested from a golden one. The
 * client wrapper (ComposeClient) only wires the two Server Actions in.
 */
import type { AcceptRefused, ComposeResult, ComposeState, ComposeTurnResponse, Properties } from "@/lib/types";
import { EvidenceChoice } from "./EvidenceChoice";
import { Explainer } from "./Explainer";
import type { Selection } from "./IndexView";

type Action = (formData: FormData) => void;

export function ComposeView({
  state,
  properties,
  selection,
  response = null,
  refusal = null,
  error = null,
  askAction,
  fileAction,
  pending = false,
}: {
  state: ComposeState;
  properties: Properties;
  selection: Selection;
  response?: ComposeTurnResponse | null;
  refusal?: AcceptRefused | null;
  error?: string | null;
  askAction?: Action;
  fileAction?: Action;
  pending?: boolean;
}) {
  if (!state.wired) return <SwitchedOff />;

  const conversation = response?.conversation ?? state.conversation;
  const template = response?.template ?? state.template;
  const transcript = response?.transcript ?? state.transcript;
  // A refused filing hands the box back with the sentence that was refused, so it can be fixed.
  const sentence = refusal?.sentence ?? response?.result.sentence ?? "";
  const canFile = state.drafts_wired && (refusal !== null || response?.result.ok === true);

  return (
    <>
      <ComposeExplainer />
      <div className="card">
        <p className="sentence">Compose a control</p>
        <p className="meta">
          Drafting with the <strong>{state.proposer}</strong> proposer. What compiles is the sentence
          you leave in the box, and you can edit it before anything runs.
        </p>
        {state.drafts_wired ? null : (
          <p className="meta">
            There is nowhere to file a draft: the engine was started without a drafts directory. You
            can still ask.
          </p>
        )}
      </div>

      {error ? (
        <div className="card blocked" role="alert">
          <p>{error}</p>
        </div>
      ) : null}

      {transcript.length > 0 ? (
        <div className="card">
          <p className="meta">
            <strong>This conversation</strong>
          </p>
          {transcript.map((turn, index) => (
            <div key={index} data-turn="">
              <p className="says">
                <span className="who">you</span> {turn.prose}
              </p>
              {turn.sentence ? (
                <p className="proposed">
                  <code>{turn.sentence}</code>
                </p>
              ) : null}
              {turn.question ? (
                <p className="asked">
                  <span className="who">asked</span> {turn.question}
                </p>
              ) : null}
              {turn.problems.map((problem, i) => (
                <p key={i} className="refused">
                  refused · {problem}
                </p>
              ))}
            </div>
          ))}
        </div>
      ) : null}

      {response ? <Result result={response.result} /> : null}

      {refusal ? (
        <div className="card verdict FAIL" data-refusal="">
          <p>
            <span className="badge">REFUSED</span>
          </p>
          <p className="proposed">
            <code>{refusal.sentence}</code>
          </p>
          <ul>
            {refusal.problems.map((problem, i) => (
              <li key={i}>{problem}</li>
            ))}
          </ul>
          <p className="means">Nothing was filed. Edit the sentence below and try again.</p>
        </div>
      ) : null}

      {canFile ? (
        <div className="card">
          <form action={fileAction} data-file="">
            <input type="hidden" name="conversation" value={conversation} />
            <label htmlFor="sentence">The rule, as it will be compiled</label>
            {/* Keyed on the sentence so a new proposal replaces the box's contents. */}
            <textarea key={sentence} id="sentence" name="sentence" rows={4} defaultValue={sentence} />
            <p className="meta">Edit this freely. What runs is what is in the box.</p>
            <label htmlFor="control_id">File it as</label>
            <input id="control_id" name="control_id" placeholder="guest_email_on_file" required />
            <label htmlFor="name">Shown as</label>
            <input id="name" name="name" placeholder="Guest Email On File" />
            <TemplatePicker state={state} current={template} id="file-template" />
            <EvidenceChoice properties={properties} selection={selection} />
            <p className="meta">
              Filing writes an unreviewed draft. Running it then spends provider calls, once.
            </p>
            <button type="submit" disabled={pending}>
              File as draft and run it
            </button>
          </form>
        </div>
      ) : null}

      <div className="card">
        <form action={askAction} data-ask="">
          <input type="hidden" name="conversation" value={conversation} />
          <label htmlFor="prose">Describe the rule</label>
          <textarea
            id="prose"
            name="prose"
            rows={3}
            placeholder="a reservation cannot be closed while the guest still owes money"
            required
          />
          <TemplatePicker state={state} current={template} id="template" />
          <button type="submit" disabled={pending}>
            Ask
          </button>
        </form>
      </div>
    </>
  );
}

function Result({ result }: { result: ComposeResult }) {
  if (result.is_question && !result.sentence) {
    return (
      <div className="card verdict UNKNOWN" data-result="">
        <p>
          <span className="badge">A QUESTION, NOT A RULE</span>
        </p>
        <p className="says">{result.question}</p>
        <p className="means">
          The proposer declined to guess at hotel policy. Answer it below and it will try again - a
          question is a better answer than a rule the hotel did not ask for.
        </p>
      </div>
    );
  }
  if (!result.ok) {
    return (
      <div className="card verdict FAIL" data-result="">
        <p>
          <span className="badge">REFUSED</span>
        </p>
        {result.sentence ? (
          <p className="proposed">
            <code>{result.sentence}</code>
          </p>
        ) : null}
        <ul>
          {(result.problems.length ? result.problems : ["No reason was recorded, which is itself a defect."]).map(
            (problem, i) => (
              <li key={i}>{problem}</li>
            ),
          )}
        </ul>
        <p className="means">
          This is the same gate a hand-written rule goes through, and it names what is missing rather
          than guessing. Rephrase below.
        </p>
      </div>
    );
  }
  return (
    <div className="card verdict PASS" data-result="">
      <p>
        <span className="badge">THIS COMPILES</span>
      </p>
      <p className="means">
        The grammar parsed it and the validator accepted it. Nothing has been filed or run yet. What
        runs is what is in the box below.
      </p>
      <p className="meta">
        Reads {result.fields.length} field(s): {result.fields.join(", ")}
      </p>
    </div>
  );
}

function TemplatePicker({ state, current, id }: { state: ComposeState; current: string; id: string }) {
  return (
    <>
      <label htmlFor={id}>Records to check</label>
      <select id={id} name="template" defaultValue={current}>
        {state.templates.map(({ control_id, entity }) => (
          <option key={control_id} value={control_id}>
            {control_id} · one record is one {entity}
          </option>
        ))}
      </select>
      <p className="meta">Borrowed from an existing control, because a sentence may not name an endpoint or a date window.</p>
    </>
  );
}

function SwitchedOff() {
  return (
    <>
      <ComposeExplainer />
      <div className="card blocked">
        <p className="sentence">No proposer is wired</p>
        <p>
          The compose window is opt-in, because it is the only part of this system that talks to a
          model at all. The engine imports nothing outside the standard library; every model backend
          is handed in at startup. Nothing is missing and nothing is broken.
        </p>
        <p className="meta">Start the engine with one of:</p>
        <pre>
          {"HOTELCONTROLS_COMPOSE=1 python3 -m tools.serve --llm stub    # fixed replies, nothing to install\n" +
            "HOTELCONTROLS_COMPOSE=1 python3 -m tools.serve --llm local   # a model on this machine, free"}
        </pre>
      </div>
    </>
  );
}

function ComposeExplainer() {
  return (
    <Explainer lede="Describe a rule in your own words. A model rewrites it as one restricted sentence, and the same deterministic grammar that compiles every hand-written rule decides whether it is one.">
      <p>
        <strong>A model never decides a rule.</strong> It drafts a sentence. The grammar compiles it
        or refuses it, and a person presses the button - so no answer anywhere in this system depends
        on a model call.
      </p>
      <p>
        <strong>What runs is the sentence in the box, not your prose.</strong> Edit it freely before
        filing.
      </p>
      <p>
        <strong>A filed draft is runnable but unreviewed.</strong> It is badged wherever it appears
        and not counted in the figure that reports how many controls reach an answer.
      </p>
      <p>
        <strong>A question is a valid answer.</strong> If the proposer will not invent hotel policy it
        asks you instead, and there is nothing to file.
      </p>
    </Explainer>
  );
}
