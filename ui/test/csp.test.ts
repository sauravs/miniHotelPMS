/**
 * The policy this surface sends. The engine's surface pins its own verbatim; this pins the
 * properties that make this one a real policy rather than a decorative one.
 */
import { describe, expect, it } from "vitest";
import { policy } from "@/proxy";

const directives = (header: string) =>
  Object.fromEntries(header.split("; ").map((d) => [d.split(" ")[0], d.split(" ").slice(1)]));

describe("the Content-Security-Policy", () => {
  const production = directives(policy("abc123", false));

  it("allows a script only from this origin AND with this request's nonce", () => {
    expect(production["script-src"]).toEqual(["'self'", "'nonce-abc123'", "'strict-dynamic'"]);
  });

  it("never allows inline script or eval in production", () => {
    const header = policy("abc123", false);
    expect(header).not.toContain("unsafe-inline");
    expect(header).not.toContain("unsafe-eval");
  });

  it("allows eval in development only, where React needs it for error stacks", () => {
    expect(policy("abc123", true)).toContain("'unsafe-eval'");
  });

  it("loads nothing from another origin, frames nowhere, embeds nothing, posts only home", () => {
    expect(production["default-src"]).toEqual(["'self'"]);
    expect(production["connect-src"]).toEqual(["'self'"]);
    expect(production["object-src"]).toEqual(["'none'"]);
    expect(production["frame-ancestors"]).toEqual(["'none'"]);
    expect(production["base-uri"]).toEqual(["'none'"]);
    expect(production["form-action"]).toEqual(["'self'"]);
    expect(policy("abc123", false)).not.toMatch(/\*|https?:/);
  });
});
