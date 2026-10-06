"use server";

import { AuthError, CredentialsSignin } from "next-auth";
import { redirect } from "next/navigation";

import { signIn } from "@/auth";

/** Only allow same-site relative redirects after sign-in (no open redirects). */
function safeCallback(value: FormDataEntryValue | null): string {
  const url = typeof value === "string" ? value : "";
  return url.startsWith("/") && !url.startsWith("//") ? url : "/dashboard";
}

export async function signInWithGoogle(formData: FormData) {
  await signIn("google", { redirectTo: safeCallback(formData.get("callbackUrl")) });
}

/** Sign in, or create an account when the form sends mode=register. */
export async function signInWithPassword(formData: FormData) {
  const mode = formData.get("mode") === "register" ? "register" : "login";
  const callbackUrl = safeCallback(formData.get("callbackUrl"));
  try {
    await signIn("password", {
      email: formData.get("email"),
      name: formData.get("name"),
      password: formData.get("password"),
      mode,
      redirectTo: callbackUrl,
    });
  } catch (error) {
    // signIn throws a redirect on success; only AuthErrors are real failures.
    if (error instanceof AuthError) {
      const code = error instanceof CredentialsSignin ? error.code : error.type;
      const query = new URLSearchParams({ error: code, callbackUrl });
      if (mode === "register") query.set("mode", "register");
      redirect(`/login?${query}`);
    }
    throw error;
  }
}
