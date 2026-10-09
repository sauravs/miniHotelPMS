/**
 * The engine's stylesheet, served on this origin - so both surfaces share ONE set of
 * criterion-2 rules, and the browser still never talks to the engine.
 *
 * A route handler and not a `rewrites()` entry, and the difference is a bug that happened: Next
 * compiles rewrites at BUILD time, so the rewrite was frozen to whichever engine address the
 * build saw, while every data request read HOTELCONTROLS_API_URL at RUN time. Pointing the UI at
 * another engine fetched data from one and the stylesheet from another - or from nothing, and
 * the page rendered unstyled. Found by running the compose window against a second engine.
 */
import { getStylesheet } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET() {
  const css = await getStylesheet();
  return new Response(css, {
    headers: { "Content-Type": "text/css; charset=utf-8", "X-Content-Type-Options": "nosniff" },
  });
}
