/**
 * Who is signed in, and the signed tenant context the engine verifies (v3 slice 24, D14).
 *
 * THE HOST AUTHENTICATES; THE ENGINE VERIFIES. This UI is the host. It keeps a person's session
 * in an HttpOnly cookie, and for every request to the engine it signs a SHORT-LIVED tenant
 * context - "about property P, for S, until T" - with the secret it shares with the engine. The
 * engine's own verifier checks it, and from then on the context, not the URL, decides which
 * property a request is about.
 *
 * Server-side only. It reads the secret, and `node:crypto` cannot run in a browser anyway; the
 * only module that sends what this signs is lib/api.ts, which no client component may import.
 * `node:crypto` is built into Node, so this adds no runtime package (the exact-pins test stays
 * as it was).
 *
 * THE WIRE FORM is the engine's, byte for byte:
 *
 *     <base64url(payload JSON)>.<base64url(HMAC-SHA256(secret, the first part))>
 *
 * with the payload's keys in sorted order and no spaces, exactly as the engine's reference
 * signer writes it - test/fixtures/auth-vector.json pins that both produce one string. Contexts
 * carry `aud: "hotelcontrols-engine"`; this UI's own session cookie carries a different `aud`,
 * so a stolen cookie cannot be replayed at the engine as a context.
 *
 * With HOTELCONTROLS_AUTH_SECRET unset, none of this runs: no sign-in, no header, and the UI is
 * the single-operator demo it has always been.
 */
import { createHmac, timingSafeEqual } from "node:crypto";

export const SECRET_VARIABLE = "HOTELCONTROLS_AUTH_SECRET";
export const CONTEXT_HEADER = "X-HotelControls-Context";
export const SESSION_COOKIE = "hc_session";

const ENGINE_AUDIENCE = "hotelcontrols-engine";
const SESSION_AUDIENCE = "hotelcontrols-ui-session";

/** A context lives one minute: signed per request, so it never needs to live longer. */
export const CONTEXT_SECONDS = 60;
/** A signed-in session lasts a working day. */
export const SESSION_SECONDS = 8 * 60 * 60;

export interface Identity {
  user: string;
  property: string;
}

/** The shared secret, or null when authentication is off. Read at RUN time, never built in. */
export function secret(): string | null {
  const value = process.env[SECRET_VARIABLE];
  return value === undefined ? null : value;
}

export const nowSeconds = () => Math.floor(Date.now() / 1000);

// ---------------------------------------------------------------- the token form, shared
function sealed(key: string, payload: Record<string, string | number>): string {
  // Keys in sorted order, compact: the engine's reference signer writes the same bytes.
  const ordered = Object.fromEntries(Object.keys(payload).sort().map((k) => [k, payload[k]]));
  const text = Buffer.from(JSON.stringify(ordered), "utf8").toString("base64url");
  const mac = createHmac("sha256", key).update(text, "ascii").digest("base64url");
  return `${text}.${mac}`;
}

function opened(key: string, token: string, audience: string, now: number): Record<string, unknown> | null {
  const parts = token.split(".");
  if (parts.length !== 2 || !parts[0] || !parts[1]) return null;
  const expected = createHmac("sha256", key).update(parts[0], "ascii").digest();
  const given = Buffer.from(parts[1], "base64url");
  // Compared in constant time, and only then is anything the token says read.
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) return null;
  let payload: unknown;
  try {
    payload = JSON.parse(Buffer.from(parts[0], "base64url").toString("utf8"));
  } catch {
    return null;
  }
  if (typeof payload !== "object" || payload === null) return null;
  const body = payload as Record<string, unknown>;
  if (body.v !== 1 || body.aud !== audience) return null;
  if (typeof body.exp !== "number" || body.exp <= now) return null;
  return body;
}

// ---------------------------------------------------------------- the engine's context
/** A tenant context for the engine. Pure: the secret and the expiry are arguments. */
export function signContext(key: string, property: string, subject: string, expires: number): string {
  return sealed(key, { v: 1, aud: ENGINE_AUDIENCE, property, sub: subject, exp: expires });
}

// ---------------------------------------------------------------- this UI's session
/** The session cookie's value for a person who has just signed in. */
export function signSession(key: string, identity: Identity, expires: number): string {
  return sealed(key, { v: 1, aud: SESSION_AUDIENCE, user: identity.user, property: identity.property, exp: expires });
}

/** Who a session cookie says is signed in - or null if it is missing, forged, foreign or expired. */
export function readSession(key: string, token: string | undefined, now: number): Identity | null {
  if (!token) return null;
  const body = opened(key, token, SESSION_AUDIENCE, now);
  if (!body || typeof body.user !== "string" || typeof body.property !== "string") return null;
  if (!body.user || !body.property) return null;
  return { user: body.user, property: body.property };
}
