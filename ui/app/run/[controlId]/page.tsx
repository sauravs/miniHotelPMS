/**
 * Ask a control a question: which property, which body of evidence. Running nothing on GET.
 *
 * Everything this page reads is free - the spec and the property list. The run itself is behind
 * the button, as a POST (see actions.ts), so loading or prefetching this page costs nothing.
 */
import { notFound } from "next/navigation";
import { getControls, getProperties } from "@/lib/api";
import { startRun } from "./actions";

export const dynamic = "force-dynamic";

export default async function AskPage({ params }: { params: Promise<{ controlId: string }> }) {
  const { controlId } = await params;
  const [{ controls }, properties] = await Promise.all([getControls(), getProperties()]);
  const control = controls.find((entry) => entry.control_id === controlId);
  if (!control) notFound();

  return (
    <div className="card">
      <p className="sentence">{control.natural_language}</p>
      <p className="meta">
        <strong>{control.name}</strong> · <code>{control.control_id}</code>
      </p>
      <form action={startRun}>
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
                  defaultChecked={property.id === properties.default.property}
                />{" "}
                <strong>{property.name}</strong> ({property.provider})
              </label>{" "}
              <label>
                evidence{" "}
                <select name={`evidence:${property.id}`} defaultValue={property.default_capture}>
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
