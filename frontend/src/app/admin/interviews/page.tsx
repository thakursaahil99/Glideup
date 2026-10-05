import type { Metadata } from "next";

import { InterviewsAdmin } from "@/components/admin/interviews-admin";
import { requirePermission } from "@/lib/session";

export const metadata: Metadata = { title: "Interviews" };

export default async function AdminInterviewsPage() {
  await requirePermission("interviews:manage", "/admin/interviews");
  return <InterviewsAdmin />;
}
