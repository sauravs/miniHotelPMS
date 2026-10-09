/**
 * The shell every page shares: a whole document, its language declared, a skip link, and the
 * engine's own stylesheet.
 *
 * ONE STYLESHEET FOR BOTH SURFACES. `/style.css` is rewritten to the engine (next.config.mjs),
 * and the markup here uses the engine's class names. The criterion-2 rules - four hues, four
 * border styles - therefore have exactly one source, and tests/unit/test_web_routing.py already
 * parses it. A second copy here would be a second set of rules free to drift from the first.
 */
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Shell } from "@/components/Shell";

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
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
