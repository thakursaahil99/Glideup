import type { Metadata } from "next";

import { JobDetailView } from "@/components/jobs/job-detail";

export const metadata: Metadata = { title: "Job" };

export default async function JobPage({ params }: PageProps<"/jobs/[jobId]">) {
  const { jobId } = await params;
  return <JobDetailView jobId={jobId} />;
}
