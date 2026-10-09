/**
 * The chrome every page shares: a skip link, the masthead, and `<main>`. Its own component so
 * the real-browser tests (e2e/) render the SAME chrome the app does - an accessibility pass over
 * a stand-in shell would be a pass over a page nobody ships.
 */
import type { ReactNode } from "react";

export function Shell({ children }: { children: ReactNode }) {
  return (
    <>
      <a className="skip" href="#main">
        Skip to the content
      </a>
      <header className="masthead">
        <div>
          <h1>
            <a href="/">Hotel control engine</a>
          </h1>
          <p>Every answer traces to the fields that produced it.</p>
        </div>
      </header>
      <main id="main">{children}</main>
    </>
  );
}
