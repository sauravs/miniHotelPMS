/**
 * The signed-in person, read from this request's cookie, and the header that carries them to the
 * engine (v3 slice 24). Server-side only: it reads the request's cookies and the shared secret.
 *
 * With authentication off (no HOTELCONTROLS_AUTH_SECRET) nobody is signed in and no header is
 * sent, which is the single-operator demo exactly. With it on, every engine request carries a
 * context signed a moment ago for the signed-in person's ONE property - and a request with nobody
 * signed in is sent to the sign-in page rather than to the engine, which would refuse it anyway.
 */
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import {
  CONTEXT_HEADER,
  CONTEXT_SECONDS,
  type Identity,
  SESSION_COOKIE,
  nowSeconds,
  readSession,
  secret,
  signContext,
} from "./auth";

/** Who is signed in on this request, or null - always null when authentication is off. */
export async function currentIdentity(): Promise<Identity | null> {
  const key = secret();
  if (key === null) return null;
  const jar = await cookies();
  return readSession(key, jar.get(SESSION_COOKIE)?.value, nowSeconds());
}

/**
 * The headers an engine request carries. None with authentication off; a fresh one-minute context
 * with it on. The property in it is the SESSION's, never one taken from a URL: the engine would
 * overrule a URL anyway, and the UI should not even ask.
 */
export async function contextHeaders(): Promise<Record<string, string>> {
  const key = secret();
  if (key === null) return {};
  const identity = await currentIdentity();
  if (!identity) redirect("/login");
  return { [CONTEXT_HEADER]: signContext(key, identity.property, identity.user, nowSeconds() + CONTEXT_SECONDS) };
}
