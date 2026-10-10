// @vitest-environment node
/**
 * v3 slice 24 (D14): this UI is the host that signs; the engine verifies.
 *
 * What must hold, because each failure would look fine on screen:
 *   - the context this UI signs is the engine's wire form byte for byte (a shared vector, also
 *     asserted by the engine's suite), or every request would be a 401;
 *   - the context names the SIGNED-IN person's property, never the one in a URL;
 *   - with authentication off, no header is sent and nothing changes;
 *   - a session cookie cannot be replayed at the engine, and a forged or expired one signs nobody
 *     in;
 *   - the development user store answers one way for a wrong user and a wrong password.
 */
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const jar: Record<string, string> = {};
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: (name: string) => (name in jar ? { value: jar[name] } : undefined) }),
}));
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`REDIRECT ${url}`);
  },
}));

import { CONTEXT_HEADER, SESSION_COOKIE, nowSeconds, readSession, signContext, signSession } from "@/lib/auth";
import { checkDevUser, parseDevUsers } from "@/lib/devUsers";
import { contextHeaders } from "@/lib/session";

const vector = JSON.parse(readFileSync(new URL("./fixtures/auth-vector.json", import.meta.url), "utf8"));
const SECRET = "ui-test-secret-" + "z".repeat(40);

const payloadOf = (token: string) => JSON.parse(Buffer.from(token.split(".")[0], "base64url").toString("utf8"));

beforeEach(() => {
  for (const key of Object.keys(jar)) delete jar[key];
  delete process.env.HOTELCONTROLS_AUTH_SECRET;
});
afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.HOTELCONTROLS_AUTH_SECRET;
});

describe("the context is the engine's wire form", () => {
  it("signs the shared vector to the engine's exact string", () => {
    expect(signContext(vector.secret, vector.property, vector.sub, vector.exp)).toBe(vector.token);
  });

  it("is two base64url parts, the first a payload addressed to the engine", () => {
    const token = signContext(SECRET, "sandbox", "alice", 2_000_000_000);
    expect(token).toMatch(/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/);
    expect(payloadOf(token)).toEqual({ aud: "hotelcontrols-engine", exp: 2_000_000_000, property: "sandbox", sub: "alice", v: 1 });
  });
});

describe("the session cookie", () => {
  const later = nowSeconds() + 600;

  it("round-trips the signed-in person", () => {
    const token = signSession(SECRET, { user: "alice", property: "sandbox" }, later);
    expect(readSession(SECRET, token, nowSeconds())).toEqual({ user: "alice", property: "sandbox" });
  });

  it("signs nobody in when it is expired, forged, tampered with or missing", () => {
    const token = signSession(SECRET, { user: "alice", property: "sandbox" }, later);
    expect(readSession(SECRET, token, later + 1)).toBeNull();
    expect(readSession("another-secret-" + "q".repeat(40), token, nowSeconds())).toBeNull();
    const other = signSession(SECRET, { user: "bob", property: "demo" }, later);
    expect(readSession(SECRET, `${other.split(".")[0]}.${token.split(".")[1]}`, nowSeconds())).toBeNull();
    expect(readSession(SECRET, undefined, nowSeconds())).toBeNull();
  });

  it("is not a context, and a context is not a session: their audiences differ", () => {
    const context = signContext(SECRET, "sandbox", "alice", later);
    expect(readSession(SECRET, context, nowSeconds())).toBeNull();
    const session = signSession(SECRET, { user: "alice", property: "sandbox" }, later);
    expect(payloadOf(session).aud).not.toBe("hotelcontrols-engine");
  });
});

describe("the header every engine request carries", () => {
  it("is absent with authentication off - the demo exactly", async () => {
    expect(await contextHeaders()).toEqual({});
  });

  it("names the signed-in person's property, signed a moment ago, for one minute", async () => {
    process.env.HOTELCONTROLS_AUTH_SECRET = SECRET;
    jar[SESSION_COOKIE] = signSession(SECRET, { user: "alice", property: "sandbox" }, nowSeconds() + 600);
    const headers = await contextHeaders();
    const payload = payloadOf(headers[CONTEXT_HEADER]);
    expect(payload.property).toBe("sandbox");
    expect(payload.sub).toBe("alice");
    expect(payload.exp - nowSeconds()).toBeLessThanOrEqual(60);
  });

  it("sends somebody who is not signed in to the sign-in page instead of the engine", async () => {
    process.env.HOTELCONTROLS_AUTH_SECRET = SECRET;
    await expect(contextHeaders()).rejects.toThrow("REDIRECT /login");
  });

  it("asks the engine about the session's property even when a page names another", async () => {
    process.env.HOTELCONTROLS_AUTH_SECRET = SECRET;
    jar[SESSION_COOKIE] = signSession(SECRET, { user: "alice", property: "sandbox" }, nowSeconds() + 600);
    const fetch = vi.fn(async () => ({ ok: true, json: async () => ({ property: "sandbox", records: [] }) }));
    vi.stubGlobal("fetch", fetch);
    const { getQueue } = await import("@/lib/api");
    await getQueue("demo");
    const [, init] = fetch.mock.calls[0] as unknown as [string, { headers: Record<string, string> }];
    expect(payloadOf(init.headers[CONTEXT_HEADER]).property).toBe("sandbox");
  });

  it("sends no context with authentication off", async () => {
    const fetch = vi.fn(async () => ({ ok: true, json: async () => ({ controls: [] }) }));
    vi.stubGlobal("fetch", fetch);
    const { getControls } = await import("@/lib/api");
    await getControls();
    const [, init] = fetch.mock.calls[0] as unknown as [string, { headers: Record<string, string> }];
    expect(init.headers[CONTEXT_HEADER]).toBeUndefined();
  });
});

describe("the development user store - a stand-in", () => {
  const users = parseDevUsers("alice:sandbox:correct-horse,bob:demo:pass:with:colons,broken-entry");

  it("reads each well-formed entry and skips a malformed one", () => {
    expect(users).toEqual([
      { user: "alice", property: "sandbox", password: "correct-horse" },
      { user: "bob", property: "demo", password: "pass:with:colons" },
    ]);
    expect(parseDevUsers(undefined)).toEqual([]);
  });

  it("signs in only with the right password, and answers alike for a wrong user or password", () => {
    expect(checkDevUser(users, "alice", "correct-horse")?.property).toBe("sandbox");
    expect(checkDevUser(users, "alice", "wrong")).toBeNull();
    expect(checkDevUser(users, "mallory", "correct-horse")).toBeNull();
  });
});
