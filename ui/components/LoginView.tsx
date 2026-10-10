/**
 * The sign-in page's body (v3 slice 24). A DEVELOPMENT STAND-IN, and it says so before anything
 * else: D14 gives real sign-in to the host product's own user store, and this exists only so the
 * engine's verification of a signed tenant context can be exercised end to end.
 *
 * Rendered by a Server Component; the two forms post to Server Actions, so nothing here runs in
 * the browser and nothing here can reach the engine.
 */
import type { Identity } from "@/lib/auth";

type Action = (formData: FormData) => void | Promise<void>;

export function LoginView({
  enabled,
  identity,
  failed,
  signIn,
  signOut,
}: {
  enabled: boolean;
  identity: Identity | null;
  failed: boolean;
  signIn?: Action;
  signOut?: Action;
}) {
  return (
    <section className="card" aria-labelledby="sign-in">
      <h2 id="sign-in">Sign in</h2>
      <p className="meta" data-stand-in="">
        <strong>Development stand-in.</strong> This sign-in is not production authentication. Its
        users come from one environment variable on the machine running this UI, each bound to one
        property. In production the host product&apos;s own user store signs the context the engine
        verifies.
      </p>
      {!enabled ? (
        <p className="sentence">
          Authentication is off: this is the single-operator demo, and there is nothing to sign in
          to. <a href="/">Go to the controls</a>.
        </p>
      ) : identity ? (
        <>
          <p className="sentence">
            Signed in as <strong>{identity.user}</strong> for property <strong>{identity.property}</strong>.
            Every request this UI makes is about that property and no other.
          </p>
          <form action={signOut}>
            <button type="submit">Sign out</button>
          </form>
        </>
      ) : (
        <form action={signIn}>
          {failed ? (
            <p className="sentence" role="alert">
              Those credentials do not match a development user.
            </p>
          ) : null}
          <p>
            <label htmlFor="user">User</label> <input id="user" name="user" autoComplete="username" required />
          </p>
          <p>
            <label htmlFor="password">Password</label>{" "}
            <input id="password" name="password" type="password" autoComplete="current-password" required />
          </p>
          <button type="submit">Sign in</button>
        </form>
      )}
    </section>
  );
}
