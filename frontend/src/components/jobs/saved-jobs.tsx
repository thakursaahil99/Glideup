"use client";

import { ArrowLeft, Bookmark } from "lucide-react";
import Link from "next/link";

import { JobCard } from "@/components/jobs/job-card";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/primitives";
import { useSavedJobs } from "@/lib/api/jobs";

export function SavedJobs() {
  const saved = useSavedJobs();
  return (
    <div className="mx-auto max-w-4xl">
      <Button asChild variant="ghost" size="sm" className="mb-4">
        <Link href="/jobs">
          <ArrowLeft /> Back to search
        </Link>
      </Button>
      <PageHeader
        title="Saved jobs"
        description="Jobs you bookmarked. Tracking applications arrives in phase 8."
      />
      {saved.isError ? (
        <Card>
          <ErrorState error={saved.error} onRetry={() => saved.refetch()} />
        </Card>
      ) : saved.isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-36 w-full rounded-xl" />
          ))}
        </div>
      ) : saved.data.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Bookmark className="size-5" aria-hidden />}
            title="No saved jobs yet"
            body="Tap the bookmark on any job to keep it here."
          />
        </Card>
      ) : (
        <ul className="space-y-3">
          {saved.data.map(({ job }) => (
            <li key={job.id}>
              <JobCard job={job} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
