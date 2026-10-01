import type { Metadata } from "next";

import { AppShell } from "@/components/layout/app-shell";
import { requirePermission } from "@/lib/session";

export const metadata: Metadata = { title: { default: "Admin", template: "%s · Admin · GlideUp" } };

export default async function AdminLayout({ children }: LayoutProps<"/admin">) {
  const user = await requirePermission("admin:access", "/admin");
  return (
    <AppShell variant="admin" user={user}>
      {children}
    </AppShell>
  );
}
