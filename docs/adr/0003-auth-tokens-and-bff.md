# ADR 0003 — Auth: Auth.js session + API-issued JWTs behind a BFF proxy

- **Status:** Accepted (Phase 1)
- **Date:** 2026-10-01

## Context
The brief asks for Google sign-in via Auth.js and for the backend to issue and validate its own
access and refresh tokens. The API must stay usable by other clients later (a React Native app),
so identity cannot live only inside Next.js.

## Decision
1. **Auth.js handles the Google OAuth flow** and keeps the browser session in an encrypted,
   httpOnly cookie.
2. On sign-in, the Next.js server sends Google's `id_token` to `POST /api/v1/auth/google`.
   **FastAPI verifies it itself** (Google JWKS signature, `aud` = our client id, `iss`, expiry,
   `email_verified`) and returns GlideUp tokens. The API never trusts the frontend's claim of
   who the user is.
3. **Access tokens** are HS256 JWTs valid for 15 minutes. The API loads the user on every
   request, so suspensions and role changes apply immediately.
4. **Refresh tokens** are single-use and stored by `jti`. Refreshing revokes the old token and
   links it to its replacement. Presenting a revoked token is treated as theft: **every**
   session for that user is revoked (reuse detection).
5. **Grace window (30 s, configurable):** a token that was *just rotated* may be presented again.
   Parallel requests — several tabs, or Server Components that cannot write cookies — routinely
   refresh with the same token at once; without the window they would log the user out.
   Tokens revoked by logout or by a family revocation never get grace.
6. **Backend-for-frontend:** the browser calls same-origin `/api/backend/*`; a Next.js route
   handler attaches the access token server-side and forwards to FastAPI. `/api/auth/session`
   is filtered so tokens never reach browser JavaScript.
7. `proxy.ts` (Next 16's middleware) runs Auth.js on page navigations so an expiring token is
   refreshed and the new cookie is persisted before Server Components render.
8. A **developer login** (`/auth/dev-login`) makes the app usable before Google is configured.
   The API refuses to start with it enabled outside `local`/`test`.

## Consequences
- ✅ XSS cannot read GlideUp tokens; no CORS needed for the web app; the API URL is runtime config.
- ✅ The API is a normal OAuth-style resource server that a mobile app can use directly.
- ⚠️ One extra hop (browser → Next → API) adds ~1–3 ms locally. Acceptable; WebSockets (Phase 5)
  will connect directly to the API using a short-lived ticket issued through the BFF.
- ⚠️ HS256 means the API is the only verifier. If other services need to verify tokens, switch
  to RS256/EdDSA with a JWKS endpoint (a settings change plus key management).
