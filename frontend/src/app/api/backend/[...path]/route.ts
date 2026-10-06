/**
 * Backend-for-frontend proxy: browser -> /api/backend/<path> -> FastAPI /api/v1/<path>.
 *
 * The access token is attached here, server-side, so it never touches browser JS.
 * Wrapping with `auth(...)` lets Auth.js refresh an expiring token and write the
 * new session cookie onto this response.
 */
import { NextResponse } from "next/server";

import { auth } from "@/auth";
import { serverEnv } from "@/lib/env";

// AI-backed calls (interview turns, grading) can take a while on free hosting.
export const maxDuration = 300;

const FORWARDED_REQUEST_HEADERS = ["content-type", "accept", "idempotency-key", "x-request-id"];
const FORWARDED_RESPONSE_HEADERS = ["content-type", "x-request-id", "content-disposition"];

const handler = auth(async (request, context: { params: Promise<{ path: string[] }> }) => {
  const session = request.auth;
  if (!session?.accessToken || session.error) {
    return NextResponse.json(
      { error: { code: "unauthorized", message: "Please sign in again" } },
      { status: 401 },
    );
  }

  const { path } = await context.params;
  const target = new URL(`${serverEnv.apiUrl}/api/v1/${path.map(encodeURIComponent).join("/")}`);
  target.search = request.nextUrl.search;

  const headers = new Headers({ Authorization: `Bearer ${session.accessToken}` });
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);

  const hasBody = !["GET", "HEAD"].includes(request.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return NextResponse.json(
      { error: { code: "backend_unreachable", message: "The GlideUp API is not reachable" } },
      { status: 502 },
    );
  }

  const responseHeaders = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new NextResponse(upstream.status === 204 ? null : upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
});

export { handler as GET, handler as POST, handler as PUT, handler as PATCH, handler as DELETE };
