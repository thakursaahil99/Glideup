import type { Metadata } from "next";

import { LLMAdmin } from "@/components/admin/platform-admin";
import { requirePermission } from "@/lib/session";

export const metadata: Metadata = { title: "AI / LLM settings" };

export default async function Page() {
  await requirePermission("llm:manage", "/admin/llm");
  return <LLMAdmin />;
}
