import type { Metadata } from "next";

import { HealthAdmin } from "@/components/admin/platform-admin";
import { requirePermission } from "@/lib/session";

export const metadata: Metadata = { title: "System health" };

export default async function Page() {
  const user = await requirePermission("system:read", "/admin/health");
  return <HealthAdmin canRetry={user.permissions.includes("system:manage")} />;
}
