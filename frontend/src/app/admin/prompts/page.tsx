import type { Metadata } from "next";

import { PromptsAdmin } from "@/components/admin/prompts-admin";
import { requirePermission } from "@/lib/session";

export const metadata: Metadata = { title: "Prompt templates" };

export default async function AdminPromptsPage() {
  await requirePermission("prompts:manage", "/admin/prompts");
  return <PromptsAdmin />;
}
