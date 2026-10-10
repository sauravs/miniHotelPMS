/**
 * The shell every page shares: a whole document, its language declared, a skip link, and the
 * engine's own stylesheet.
 *
 * ONE STYLESHEET FOR BOTH SURFACES. `/style.css` is the engine's own file, served on this origin
 * by app/style.css/route.ts,
 * and the markup here uses the engine's class names. The criterion-2 rules - four hues, four
 * border styles - therefore have exactly one source, and tests/unit/test_web_routing.py already
 * parses it. A second copy here would be a second set of rules free to drift from the first.
 */
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Identity } from "@/components/Identity";
import { Shell } from "@/components/Shell";

// EVERY page renders per request, including the ones Next would otherwise prerender (its 404).
// A nonce is per request, and a page built ahead of time carries none: the prerendered 404 had
// every script refused by the CSP and never hydrated. Found by driving /nowhere live.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Hotel control engine",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="stylesheet" href="/style.css" />
      </head>
      <body>
        <Shell>
          {/* Who is signed in (slice 24) - nothing at all with authentication off. */}
          <Identity />
          {children}
        </Shell>
      </body>
    </html>
  );
}
