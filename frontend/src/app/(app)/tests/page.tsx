import type { Metadata } from "next";

import { ProblemsList } from "@/components/tests/problems-list";

export const metadata: Metadata = { title: "Coding tests" };

export default async function TestsPage({ searchParams }: PageProps<"/tests">) {
  const { lang } = await searchParams;
  return <ProblemsList language={typeof lang === "string" ? lang : null} />;
}
