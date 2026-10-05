import type { Metadata } from "next";

import { ReportsAdmin } from "@/components/admin/reports-admin";
import { requirePermission } from "@/lib/session";

export const metadata: Metadata = { title: "User reports" };

export default async function AdminReportsPage() {
  const user = await requirePermission("reports:read", "/admin/reports");
  return <ReportsAdmin canManage={user.permissions.includes("reports:manage")} />;
}
