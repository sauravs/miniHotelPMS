/**
 * The question a run asks: this control, this property, this body of evidence. Pure, so it can
 * be tested from the golden payloads; the page around it does the fetching.
 *
 * The form POSTs to a Server Action (trap 4): running spends provider calls and writes the store,
 * so it happens only when a person presses the button - never on a page load or a prefetch.
 */
import type { ControlEntry, Properties } from "@/lib/types";
import type { Selection } from "./IndexView";

export function AskForm({
  control,
  properties,
  selection,
  action,
}: {
  control: ControlEntry;
  properties: Properties;
  selection: Selection;
  action?: (formData: FormData) => Promise<void>;
}) {
  return (
    <div className="card">
      <p className="sentence">{control.natural_language}</p>
      <p className="meta">
        <strong>{control.name}</strong> · <code>{control.control_id}</code>
        {control.reviewed ? null : (
          <>
            {" "}
            <span className="draft-badge">draft · unreviewed</span>
          </>
        )}
      </p>
      {control.readiness.map((report) => (
        <p key={report.provider} className={`readiness${report.executable ? "" : " short"}`}>
          {report.headline}
        </p>
      ))}
      <form action={action}>
        <input type="hidden" name="control_id" value={control.control_id} />
        <fieldset>
          <legend>Which property, and which body of evidence</legend>
          {properties.properties.map((property) => (
            <div key={property.id}>
              <label>
                <input
                  type="radio"
                  name="property"
                  value={property.id}
                  defaultChecked={property.id === selection.property}
                />{" "}
                <strong>{property.name}</strong> ({property.provider})
              </label>{" "}
              <label>
                evidence{" "}
                <select
                  name={`evidence:${property.id}`}
                  defaultValue={property.id === selection.property ? selection.evidence : property.default_capture}
                >
                  {property.captures.map((capture) => (
                    <option key={capture} value={capture}>
                      {capture}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ))}
        </fieldset>
        <p className="meta">
          Running spends provider calls - for some evidence, one per record. The result is saved,
          and re-reading it afterwards costs nothing.
        </p>
        <button type="submit">Run this control</button>
      </form>
    </div>
  );
}
