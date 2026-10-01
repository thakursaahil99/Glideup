import "server-only";

import { notFound, redirect } from "next/navigation";

import { auth } from "@/auth";
import type { MenuUser } from "@/components/layout/user-menu";

/**
 * Server-side guard for layouts/pages. proxy.ts already redirects signed-out users;
 * this is defense in depth. Authorization is always re-checked by the API.
 */
export async function requireUser(callbackUrl: string): Promise<MenuUser> {
  const session = await auth();
  if (!session?.user || session.error) {
    redirect(`/login?callbackUrl=${encodeURIComponent(callbackUrl)}`);
  }
  const { name, email, image, roles, permissions } = session.user;
  return { name, email, image, roles: roles ?? [], permissions: permissions ?? [] };
}

export async function requirePermission(permission: string, callbackUrl: string): Promise<MenuUser> {
  const user = await requireUser(callbackUrl);
  // 404 rather than 403: don't advertise that an admin area exists.
  if (!user.permissions.includes(permission)) notFound();
  return user;
}
