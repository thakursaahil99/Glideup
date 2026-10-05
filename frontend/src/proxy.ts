/**
 * Runs before page requests. Auth.js checks the session here (see `authorized` in
 * auth.ts), redirects signed-out users to /login, and — importantly — refreshes an
 * expiring access token and persists the new cookie, which Server Components cannot do.
 */
export { auth as proxy } from "@/auth";

export const config = {
  // Pages only: skip Next internals, static files and API routes (the BFF refreshes itself).
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|icons|manifest.webmanifest|sw.js|offline.html|.*\\.(?:svg|png|jpg|jpeg|webp|ico)$).*)",
  ],
};
