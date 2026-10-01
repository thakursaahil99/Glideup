import type { Metadata } from "next";
import { Suspense } from "react";

import { JobsSearch } from "@/components/jobs/jobs-search";
import { Skeleton } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "Jobs" };

export default function JobsPage() {
  // useSearchParams needs a Suspense boundary.
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-6xl" />}>
      <JobsSearch />
    </Suspense>
  );
}
