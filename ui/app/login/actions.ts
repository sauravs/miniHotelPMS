"use server";
/**
 * Signing in and out (v3 slice 24) - against the DEVELOPMENT STAND-IN user store, lib/devUsers.ts.
 *
 * Server Actions, so both are POSTs a person makes on purpose. Signing in sets an HttpOnly,
 * same-site session cookie signed with the shared secret under its OWN audience, so it can never
 * be replayed at the engine as a tenant context. Nothing here talks to the engine.
 */
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE, SESSION_SECONDS, nowSeconds, secret, signSession } from "@/lib/auth";
import { checkDevUser, devUsers } from "@/lib/devUsers";

export async function signIn(formData: FormData): Promise<void> {
  const key = secret();
  if (key === null) redirect("/");
  const found = checkDevUser(devUsers(), String(formData.get("user") ?? ""), String(formData.get("password") ?? ""));
  // One answer for an unknown user and a wrong password, so the page cannot be used to learn names.
  if (!found) redirect("/login?error=1");
  (await cookies()).set(
    SESSION_COOKIE,
    signSession(key, { user: found.user, property: found.property }, nowSeconds() + SESSION_SECONDS),
    {
      httpOnly: true,
      sameSite: "strict",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: SESSION_SECONDS,
    },
  );
  redirect("/");
}

export async function signOut(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/login");
}
