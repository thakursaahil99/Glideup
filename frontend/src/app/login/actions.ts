"use server";

import { AuthError } from "next-auth";
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

export async function signInForDevelopment(formData: FormData) {
  try {
    await signIn("dev-login", {
      email: formData.get("email"),
      name: formData.get("name"),
      redirectTo: safeCallback(formData.get("callbackUrl")),
    });
  } catch (error) {
    // signIn throws a redirect on success; only AuthErrors are real failures.
    if (error instanceof AuthError) redirect(`/login?error=${error.type}`);
    throw error;
  }
}
