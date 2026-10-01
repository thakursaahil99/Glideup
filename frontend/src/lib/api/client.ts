/**
 * Typed browser client for the GlideUp API, generated from FastAPI's OpenAPI schema
 * (`npm run gen:api`). Requests go to the same-origin BFF proxy (/api/backend/*),
 * which attaches the access token server-side.
 */
import createClient from "openapi-fetch";

import type { paths } from "./schema";

const API_PREFIX = "/api/v1/";
const BFF_PREFIX = "/api/backend/";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId?: string | null,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function bffFetch(request: Request): Promise<Response> {
  const url = new URL(request.url);
  if (url.pathname.startsWith(API_PREFIX)) {
    url.pathname = BFF_PREFIX + url.pathname.slice(API_PREFIX.length);
  }
  const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer();
  return fetch(url, {
    method: request.method,
    headers: request.headers,
    body,
    credentials: "same-origin",
    signal: request.signal,
  });
}

export const api = createClient<paths>({
  baseUrl: typeof window === "undefined" ? "http://localhost" : window.location.origin,
  fetch: bffFetch,
});

type Result<T> = { data?: T; error?: unknown; response: Response };

/** Return the data or throw an `ApiError` built from the backend's error envelope. */
export async function unwrap<T>(promise: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await promise;
  if (response.ok) return data as T;
  const envelope = (
    error as { error?: { code?: string; message?: string; request_id?: string; details?: unknown } }
  )?.error;
  throw new ApiError(
    response.status,
    envelope?.code ?? "http_error",
    envelope?.message ?? `Request failed (${response.status})`,
    envelope?.request_id ?? response.headers.get("x-request-id"),
    envelope?.details,
  );
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.requestId ? `${error.message} (ref ${error.requestId.slice(0, 8)})` : error.message;
  }
  return error instanceof Error ? error.message : "Something went wrong";
}
