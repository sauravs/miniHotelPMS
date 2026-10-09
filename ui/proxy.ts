/**
 * A real Content-Security-Policy for this surface, with a fresh nonce per request.
 *
 * The engine's surface sends `default-src 'none'` and runs no script at all. This one cannot -
 * React hydrates - so the next-strongest thing: scripts only from this origin AND carrying this
 * request's nonce, nothing inline without it, nothing from anywhere else, no plugins, no
 * framing, forms posting only back here. React escapes by default; this is the second lock, the
 * one the engine's surface has in `server.py`, and guest names and free-text remarks from booking
 * channels are exactly what it is for.
 *
 * Every page here is dynamically rendered (`force-dynamic`), which a nonce requires: a page
 * built ahead of time has no request to take a nonce from.
 *
 * Not `upgrade-insecure-requests`: the demo runs over plain http on 127.0.0.1, and upgrading
 * its own stylesheet request to https would leave it unstyled.
 */
import { type NextRequest, NextResponse } from "next/server";

export function policy(nonce: string, development: boolean): string {
  return [
    "default-src 'self'",
    // `'unsafe-eval'` in development only: React uses eval to rebuild server error stacks there,
    // and never in production.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${development ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' 'nonce-${nonce}'`,
    "img-src 'self'",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const header = policy(nonce, process.env.NODE_ENV === "development");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", header);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", header);
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!_next/static|_next/image|favicon.ico|style.css).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
