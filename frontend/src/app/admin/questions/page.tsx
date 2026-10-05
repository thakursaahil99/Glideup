import type { Metadata } from "next";

import { QuestionBankAdmin } from "@/components/admin/question-bank";
import { requirePermission } from "@/lib/session";

export const metadata: Metadata = { title: "Question bank" };

export default async function AdminQuestionsPage() {
  await requirePermission("questions:manage", "/admin/questions");
  return <QuestionBankAdmin />;
}
