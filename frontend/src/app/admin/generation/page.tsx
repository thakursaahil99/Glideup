import type { Metadata } from "next";

import { GenerationQueueAdmin } from "@/components/admin/generation-queue";
import { requirePermission } from "@/lib/session";

export const metadata: Metadata = { title: "AI generation queue" };

export default async function AdminGenerationPage() {
  await requirePermission("questions:manage", "/admin/generation");
  return <GenerationQueueAdmin />;
}
