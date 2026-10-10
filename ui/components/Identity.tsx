/**
 * Who is signed in, above every page (v3 slice 24) - or nothing at all with authentication off,
 * so the demo looks exactly as it did. Labelled a development stand-in wherever it shows.
 */
import { signOut } from "@/app/login/actions";
import { currentIdentity } from "@/lib/session";

export async function Identity() {
  const who = await currentIdentity();
  if (!who) return null;
  return (
    <div className="meta" data-identity="">
      Signed in as <strong>{who.user}</strong> for property <strong>{who.property}</strong> (development sign-in, a
      stand-in).{" "}
      <form action={signOut}>
        <button type="submit">Sign out</button>
      </form>
    </div>
  );
}
