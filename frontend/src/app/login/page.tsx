import { AlertCircle, Terminal } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { auth } from "@/auth";
import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/primitives";
import { serverEnv } from "@/lib/env";

import { signInForDevelopment, signInWithGoogle } from "./actions";

export const metadata: Metadata = { title: "Sign in" };

const ERROR_MESSAGES: Record<string, string> = {
  account_suspended: "This account has been suspended. Contact support if you think this is a mistake.",
  email_not_verified: "Your Google email address isn't verified yet.",
  CredentialsSignin: "Wrong email or password.",
  backend_unreachable: "We couldn't reach the GlideUp API. Please try again in a moment.",
  SessionExpired: "Your session has expired. Please sign in again.",
};

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className="size-4">
      <path
        fill="#4285F4"
        d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.4h6.5a5.6 5.6 0 0 1-2.4 3.6v3h3.9c2.2-2.1 3.5-5.1 3.5-8.7Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.2 0 6-1.1 8-2.9l-3.9-3c-1.1.7-2.5 1.2-4.1 1.2-3.1 0-5.8-2.1-6.7-5H1.2v3.1A12 12 0 0 0 12 24Z"
      />
      <path fill="#FBBC05" d="M5.3 14.3a7.2 7.2 0 0 1 0-4.6V6.6H1.2a12 12 0 0 0 0 10.8l4.1-3.1Z" />
      <path
        fill="#EA4335"
        d="M12 4.8c1.8 0 3.3.6 4.6 1.8l3.4-3.4A11.5 11.5 0 0 0 12 0 12 12 0 0 0 1.2 6.6l4.1 3.1c.9-2.9 3.6-4.9 6.7-4.9Z"
      />
    </svg>
  );
}

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const params = await searchParams;
  const callbackUrl = typeof params.callbackUrl === "string" ? params.callbackUrl : "/dashboard";
  const errorCode = typeof params.error === "string" ? params.error : undefined;

  const session = await auth();
  if (session?.user && !session.error) redirect(callbackUrl.startsWith("/") ? callbackUrl : "/dashboard");

  const errorMessage = errorCode
    ? (ERROR_MESSAGES[errorCode] ?? "Sign-in didn't work. Please try again.")
    : session?.error
      ? ERROR_MESSAGES.SessionExpired
      : undefined;
  const noProviders = !serverEnv.googleEnabled && !serverEnv.devLoginEnabled;

  return (
    <main
      id="main"
      className="flex min-h-dvh flex-col items-center justify-center px-4 py-12"
      style={{ background: "var(--sky-gradient)" }}
    >
      <Link href="/" aria-label="GlideUp home">
        <Logo className="text-xl" />
      </Link>
      <div className="mt-8 w-full max-w-sm rounded-2xl border bg-card p-8 shadow-lg">
        <h1 className="text-2xl font-semibold">Welcome aboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">Sign in to find jobs and practice interviews.</p>

        {errorMessage && (
          <div
            role="alert"
            className="mt-5 flex gap-2 rounded-lg border border-destructive/30 bg-destructive/8 p-3 text-sm text-destructive"
          >
            <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
            <span>{errorMessage}</span>
          </div>
        )}

        {serverEnv.googleEnabled && (
          <form action={signInWithGoogle} className="mt-6">
            <input type="hidden" name="callbackUrl" value={callbackUrl} />
            <Button type="submit" variant="outline" size="lg" className="w-full">
              <GoogleIcon /> Continue with Google
            </Button>
          </form>
        )}

        {serverEnv.devLoginEnabled && (
          <form action={signInForDevelopment} className="mt-6 space-y-3 rounded-xl border border-dashed p-4">
            <p className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <Terminal className="size-3.5" aria-hidden /> Sign in with email
            </p>
            <input type="hidden" name="callbackUrl" value={callbackUrl} />
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                required
                placeholder="you@example.com"
                autoComplete="email"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="name">Name (optional)</Label>
              <Input id="name" name="name" placeholder="Sahil Thakur" autoComplete="name" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input id="password" name="password" type="password" autoComplete="current-password" />
            </div>
            <Button type="submit" className="w-full">
              Sign in
            </Button>
          </form>
        )}

        {noProviders && (
          <p className="mt-6 rounded-lg bg-muted p-3 text-sm text-muted-foreground">
            No sign-in method is configured. Set <code>AUTH_GOOGLE_ID</code> and{" "}
            <code>AUTH_GOOGLE_SECRET</code>, or <code>AUTH_DEV_LOGIN_ENABLED=true</code> for local
            development. See the README.
          </p>
        )}
      </div>
      <p className="mt-6 text-sm text-muted-foreground">
        Built by{" "}
        <Link href="/about" className="font-medium text-foreground hover:underline">
          Sahil Thakur
        </Link>
      </p>
    </main>
  );
}
