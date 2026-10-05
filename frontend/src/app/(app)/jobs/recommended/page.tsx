import type { Metadata } from "next";

import { RecommendedJobs } from "@/components/matching/recommended-jobs";

export const metadata: Metadata = { title: "Recommended for you" };

export default function RecommendedJobsPage() {
  return <RecommendedJobs />;
}
