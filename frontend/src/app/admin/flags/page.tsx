import type { Metadata } from "next";

import { FlagsAdmin } from "@/components/admin/platform-admin";
import { requirePermission } from "@/lib/session";

export const metadata: Metadata = { title: "Feature flags" };

export default async function Page() {
  await requirePermission("flags:manage", "/admin/flags");
  return <FlagsAdmin />;
}
