import type { Metadata } from "next";

import { JobsAdmin } from "@/components/admin/jobs-admin";
import { requirePermission } from "@/lib/session";

export const metadata: Metadata = { title: "Jobs & Sources" };

export default async function AdminJobsPage() {
  await requirePermission("jobs:manage", "/admin/jobs");
  return <JobsAdmin />;
}
