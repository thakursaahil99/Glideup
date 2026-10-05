import type { Metadata } from "next";

import { ProblemSolver } from "@/components/tests/problem-solver";

export const metadata: Metadata = { title: "Problem" };

export default async function ProblemPage({ params, searchParams }: PageProps<"/tests/[slug]">) {
  const { slug } = await params;
  const { lang } = await searchParams;
  return <ProblemSolver slug={slug} language={typeof lang === "string" ? lang : null} />;
}
