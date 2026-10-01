import "server-only";

/**
 * Server-side configuration, read at runtime (never inlined into the client bundle),
 * so the same image works on a laptop and in Azure with different env vars.
 */
export const serverEnv = {
  /** Where the Next.js server reaches FastAPI (e.g. http://api:8000 inside Docker). */
  apiUrl: (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, ""),
  googleEnabled: Boolean(process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET),
  devLoginEnabled: process.env.AUTH_DEV_LOGIN_ENABLED === "true",
};
