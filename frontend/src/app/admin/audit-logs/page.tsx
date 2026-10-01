import type { Metadata } from "next";

import { AuditLogViewer } from "@/components/admin/audit-log";
import { requirePermission } from "@/lib/session";

export const metadata: Metadata = { title: "Audit log" };

export default async function AdminAuditLogsPage() {
  await requirePermission("audit:read", "/admin/audit-logs");
  return <AuditLogViewer />;
}
