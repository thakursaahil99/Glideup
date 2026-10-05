import type { Metadata } from "next";
import { Suspense } from "react";

import { InterviewsHome } from "@/components/interviews/interviews-home";

export const metadata: Metadata = { title: "Mock interviews" };

export default function InterviewsPage() {
  return (
    <Suspense>
      <InterviewsHome />
    </Suspense>
  );
}
