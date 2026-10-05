import type { Metadata } from "next";

import { AttemptView } from "@/components/tests/attempt-view";

export const metadata: Metadata = { title: "Framework test" };

export default async function AttemptPage({ params }: PageProps<"/tests/attempts/[attemptId]">) {
  const { attemptId } = await params;
  return <AttemptView attemptId={attemptId} />;
}
