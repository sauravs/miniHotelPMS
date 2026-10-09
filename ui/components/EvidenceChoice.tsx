/**
 * Which property, and which body of evidence - one radio per property, each with its captures.
 * Shared by the ask form and the compose window's file form, so "where will this run?" is asked
 * the same way everywhere. The chosen capture arrives as `evidence:<property>`.
 */
import type { Properties } from "@/lib/types";
import type { Selection } from "./IndexView";

export function EvidenceChoice({ properties, selection }: { properties: Properties; selection: Selection }) {
  return (
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
  );
}
