/**
 * THE DEVELOPMENT USER STORE - A STAND-IN, AND LABELLED AS ONE WHEREVER IT SHOWS (v3 slice 24).
 *
 * D14 puts real sign-in in the HOST: a hotel group's own portal, with its own user store. This
 * repository has no such product, so the UI carries the smallest stand-in that lets the engine's
 * verification be exercised end to end, and says what it is on the sign-in page itself.
 *
 * What it is NOT, so nobody mistakes it for more: not production authentication, not a password
 * store, not hashed at rest. Users come from ONE environment variable on the machine running the
 * UI - never from a file in this repository - in the form
 *
 *     HOTELCONTROLS_UI_DEV_USERS="alice:sandbox:a-long-dev-password,bob:demo:another-one"
 *
 * Each user is bound to exactly one property, and that is the property every context signed for
 * them names. Unset, nobody can sign in, and with authentication on that is the safe answer.
 */
import { createHash, timingSafeEqual } from "node:crypto";

export const DEV_USERS_VARIABLE = "HOTELCONTROLS_UI_DEV_USERS";

export interface DevUser {
  user: string;
  property: string;
  password: string;
}

/** The configured stand-in users. A malformed entry is skipped rather than half-read. */
export function parseDevUsers(raw: string | undefined): DevUser[] {
  if (!raw) return [];
  const users: DevUser[] = [];
  for (const entry of raw.split(",")) {
    const [user, property, ...rest] = entry.trim().split(":");
    const password = rest.join(":"); // a password may itself contain a colon
    if (user && property && password) users.push({ user, property, password });
  }
  return users;
}

export const devUsers = () => parseDevUsers(process.env[DEV_USERS_VARIABLE]);

const digest = (text: string) => createHash("sha256").update(text, "utf8").digest();

/**
 * The user these credentials name, or null. The password is compared in constant time over
 * equal-length digests, and an unknown user costs the same comparison as a wrong password, so
 * neither the time nor the answer says which of the two was wrong.
 */
export function checkDevUser(users: DevUser[], user: string, password: string): DevUser | null {
  const found = users.find((u) => u.user === user);
  const expected = digest(found ? found.password : "\u0000no such user\u0000");
  const matches = timingSafeEqual(expected, digest(password));
  return found && matches ? found : null;
}
