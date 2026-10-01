/**
 * Auth.js configuration.
 *
 * Auth.js owns the browser session (an encrypted, httpOnly cookie). FastAPI owns
 * identity and authorization: after Google sign-in we hand Google's id_token to the
 * backend, which verifies it and returns GlideUp access + refresh tokens. Those
 * tokens live only inside the encrypted cookie and server-side code; the browser
 * talks to FastAPI through the /api/backend proxy (see ADR 0003).
 */
import NextAuth, { type DefaultSession } from "next-auth";
import type { JWT } from "next-auth/jwt";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";
import type { Provider } from "next-auth/providers";

import type { Me, TokenResponse } from "@/lib/api/types";
import { serverEnv } from "@/lib/env";

declare module "next-auth" {
  interface Session {
    /** Server-side only: stripped from /api/auth/session before it reaches the browser. */
    accessToken?: string;
    error?: "RefreshTokenError";
    user: {
      id: string;
      roles: string[];
      permissions: string[];
    } & DefaultSession["user"];
  }
  interface User {
    glideup?: TokenResponse;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken?: string;
    refreshToken?: string;
    accessExpiresAt?: number;
    me?: Pick<Me, "id" | "email" | "name" | "avatar_url" | "roles" | "permissions">;
    error?: "RefreshTokenError";
  }
}

/** Refresh this long before expiry so in-flight requests never carry a dead token. */
const REFRESH_MARGIN_MS = 2 * 60 * 1000;

export class BackendAuthError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(code);
  }
}

async function backendAuth(path: string, body: unknown): Promise<TokenResponse> {
  const response = await fetch(`${serverEnv.apiUrl}/api/v1/auth/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new BackendAuthError(response.status, payload?.error?.code ?? "backend_error");
  }
  return (await response.json()) as TokenResponse;
}

function applyTokens(token: JWT, data: TokenResponse): JWT {
  const { id, email, name, avatar_url, roles, permissions } = data.user;
  return {
    ...token,
    sub: id,
    email,
    name,
    picture: avatar_url,
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    accessExpiresAt: Date.parse(data.access_expires_at),
    me: { id, email, name, avatar_url, roles, permissions },
    error: undefined,
  };
}

// Several requests can need a refresh at the same instant; share one backend call.
const inflightRefresh = new Map<string, Promise<TokenResponse>>();

async function refresh(token: JWT): Promise<JWT> {
  const refreshToken = token.refreshToken;
  if (!refreshToken) return { ...token, error: "RefreshTokenError" };
  let pending = inflightRefresh.get(refreshToken);
  if (!pending) {
    pending = backendAuth("refresh", { refresh_token: refreshToken });
    inflightRefresh.set(refreshToken, pending);
    pending.finally(() => setTimeout(() => inflightRefresh.delete(refreshToken), 10_000)).catch(() => {});
  }
  try {
    return applyTokens(token, await pending);
  } catch {
    return { ...token, accessToken: undefined, error: "RefreshTokenError" };
  }
}

const providers: Provider[] = [];
if (serverEnv.googleEnabled) providers.push(Google);
if (serverEnv.devLoginEnabled) {
  providers.push(
    Credentials({
      id: "dev-login",
      name: "Developer login",
      credentials: { email: { label: "Email", type: "email" }, name: { label: "Name" } },
      async authorize(credentials) {
        const email = String(credentials?.email ?? "").trim();
        if (!email) return null;
        const name = String(credentials?.name ?? "").trim() || undefined;
        try {
          const data = await backendAuth("dev-login", { email, name });
          return { id: data.user.id, email: data.user.email, name: data.user.name, glideup: data };
        } catch {
          return null;
        }
      },
    }),
  );
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers,
  session: { strategy: "jwt", maxAge: 14 * 24 * 60 * 60 },
  pages: { signIn: "/login", error: "/login" },
  callbacks: {
    async signIn({ account }) {
      if (account?.provider !== "google") return true;
      if (!account.id_token) return "/login?error=GoogleNoIdToken";
      try {
        // Same object is passed on to the jwt callback below.
        (account as { glideup?: TokenResponse }).glideup = await backendAuth("google", {
          id_token: account.id_token,
        });
        return true;
      } catch (error) {
        const code = error instanceof BackendAuthError ? error.code : "backend_unreachable";
        return `/login?error=${encodeURIComponent(code)}`;
      }
    },

    async jwt({ token, user, account }) {
      const fresh = (account as { glideup?: TokenResponse } | null)?.glideup ?? user?.glideup;
      if (fresh) return applyTokens(token, fresh);
      if (token.accessExpiresAt && Date.now() < token.accessExpiresAt - REFRESH_MARGIN_MS) {
        return token;
      }
      return refresh(token);
    },

    session({ session, token }) {
      session.accessToken = token.accessToken;
      session.error = token.error;
      if (token.me) {
        session.user = {
          ...session.user,
          id: token.me.id,
          email: token.me.email,
          name: token.me.name ?? null,
          image: token.me.avatar_url ?? null,
          roles: token.me.roles,
          permissions: token.me.permissions,
        };
      }
      return session;
    },

    /** Used by proxy.ts: which pages need a signed-in user. */
    authorized({ auth: session, request }) {
      const { pathname } = request.nextUrl;
      const needsAuth = ["/dashboard", "/admin", "/settings"].some(
        (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
      );
      return !needsAuth || Boolean(session?.user && !session.error);
    },
  },
  events: {
    async signOut(message) {
      const token = "token" in message ? message.token : null;
      if (token?.refreshToken) {
        await fetch(`${serverEnv.apiUrl}/api/v1/auth/logout`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: token.refreshToken }),
        }).catch(() => {});
      }
    },
  },
});
