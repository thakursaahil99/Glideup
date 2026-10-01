import type { NextRequest } from "next/server";

import { handlers } from "@/auth";

export const POST = handlers.POST;

/**
 * Wrap Auth.js's GET so `/api/auth/session` never sends GlideUp tokens to the
 * browser. Cookies (including refreshed sessions) are passed through untouched.
 */
export async function GET(request: NextRequest) {
  const response = await handlers.GET(request);
  if (!request.nextUrl.pathname.endsWith("/session") || !response.ok) return response;

  const session = await response.json().catch(() => null);
  if (session && typeof session === "object") delete session.accessToken;
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  return new Response(JSON.stringify(session), { status: response.status, headers });
}
