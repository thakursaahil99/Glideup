import type { Metadata } from "next";

import { AdminUserDetail } from "@/components/admin/user-detail";
import { requirePermission } from "@/lib/session";

export const metadata: Metadata = { title: "User" };

export default async function AdminUserPage({ params }: PageProps<"/admin/users/[userId]">) {
  await requirePermission("users:read", "/admin/users");
  const { userId } = await params;
  return <AdminUserDetail userId={userId} />;
}
