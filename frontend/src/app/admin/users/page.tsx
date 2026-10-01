import type { Metadata } from "next";

import { UsersAdmin } from "@/components/admin/users-table";
import { requirePermission } from "@/lib/session";

export const metadata: Metadata = { title: "Users" };

export default async function AdminUsersPage() {
  await requirePermission("users:read", "/admin/users");
  return <UsersAdmin />;
}
