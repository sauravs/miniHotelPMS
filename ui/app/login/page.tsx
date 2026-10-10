/**
 * The sign-in page (v3 slice 24). Reads nothing from the engine - a person who has not signed in
 * has no context to send it - so it renders whether or not anybody is signed in.
 */
import { LoginView } from "@/components/LoginView";
import { secret } from "@/lib/auth";
import { currentIdentity } from "@/lib/session";
import { signIn, signOut } from "./actions";

export const dynamic = "force-dynamic";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = await searchParams;
  return (
    <LoginView
      enabled={secret() !== null}
      identity={await currentIdentity()}
      failed={[query.error].flat()[0] === "1"}
      signIn={signIn}
      signOut={signOut}
    />
  );
}
