import type { Metadata } from "next";

import { SavedJobs } from "@/components/jobs/saved-jobs";

export const metadata: Metadata = { title: "Saved jobs" };

export default function SavedJobsPage() {
  return <SavedJobs />;
}
