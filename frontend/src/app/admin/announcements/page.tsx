import type { Metadata } from "next";

import { AnnouncementsAdmin } from "@/components/admin/platform-admin";
import { requirePermission } from "@/lib/session";

export const metadata: Metadata = { title: "Announcements" };

export default async function Page() {
  await requirePermission("announcements:manage", "/admin/announcements");
  return <AnnouncementsAdmin />;
}
