/**
 * The controls, each a link to the page that can run it. Deliberately minimal in this PR - the
 * index proper (readiness per provider, the evidence picker) is the next one.
 */
import Link from "next/link";
import { getControls } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Index() {
  const { controls } = await getControls();
  return (
    <div className="card">
      <p className="sentence">Controls</p>
      <ul>
        {controls.map((control) => (
          <li key={control.control_id}>
            {/* A prefetch of this link is harmless: the page it leads to runs nothing on GET. */}
            <Link href={`/run/${encodeURIComponent(control.control_id)}`}>{control.name}</Link>
            <p className="meta">{control.natural_language}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
