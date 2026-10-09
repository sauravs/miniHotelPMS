/**
 * The page explanation bar: one visible line, and the depth one keypress away.
 *
 * `<details>`, never `title=`: a tooltip is invisible on a touch screen, gone from any text
 * extraction, and announced unreliably by screen readers. This is plain HTML, works with no
 * script, and its text survives every tag being stripped. The same mechanism the engine's
 * surface uses, for the same reasons.
 */
import type { ReactNode } from "react";

export function Explainer({ lede, children }: { lede: ReactNode; children: ReactNode }) {
  return (
    <section className="explainer" aria-label="About this page">
      <p className="lede">{lede}</p>
      <details>
        <summary>How to read this page</summary>
        <div className="folded">{children}</div>
      </details>
    </section>
  );
}
