"use client";

import { ArrowLeft, FileUp, Loader2, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { JobCard } from "@/components/jobs/job-card";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/primitives";
import { type RecommendationFilters, useRecommendations } from "@/lib/api/matches";
import { cn } from "@/lib/utils";

function Toggle({
  pressed,
  onClick,
  children,
}: {
  pressed: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1 text-sm transition-colors",
        pressed ? "border-primary bg-primary-soft text-primary" : "hover:bg-accent",
      )}
    >
      {children}
    </button>
  );
}

export function RecommendedJobs() {
  const [filters, setFilters] = useState<RecommendationFilters>({ india: false, remote: false });
  const query = useRecommendations(filters);
  const first = query.data?.pages[0];
  const items = query.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div className="mx-auto max-w-4xl">
      <Button asChild variant="ghost" size="sm" className="mb-4">
        <Link href="/jobs">
          <ArrowLeft /> Back to search
        </Link>
      </Button>
      <PageHeader
        title="Recommended for you"
        description="Jobs ranked by how well they fit your resume, with a nudge for the locations and work style in your profile."
      />
      <div className="mb-4 flex flex-wrap items-center gap-2" role="group" aria-label="Narrow recommendations">
        <Toggle pressed={filters.india} onClick={() => setFilters({ ...filters, india: !filters.india })}>
          India only
        </Toggle>
        <Toggle pressed={filters.remote} onClick={() => setFilters({ ...filters, remote: !filters.remote })}>
          Remote only
        </Toggle>
        {first?.embedding_pending && (
          <span role="status" className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Finishing your profile; scores will
            sharpen in a moment.
          </span>
        )}
      </div>

      {query.isError ? (
        <Card>
          <ErrorState error={query.error} onRetry={() => query.refetch()} />
        </Card>
      ) : query.isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-40 w-full rounded-xl" />
          ))}
        </div>
      ) : !first?.available ? (
        <Card>
          <EmptyState
            icon={<FileUp className="size-5" aria-hidden />}
            title="Upload your resume to get recommendations"
            body={
              <>
                We match jobs to your skills and experience.{" "}
                <Link href="/onboarding" className="text-primary underline-offset-4 hover:underline">
                  Upload a resume
                </Link>{" "}
                to start.
              </>
            }
          />
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Sparkles className="size-5" aria-hidden />}
            title="No recommendations with these filters"
            body="Try turning a filter off, or add more skills to your profile."
          />
        </Card>
      ) : (
        <>
          <ul className="space-y-3">
            {items.map(({ job, reasons }) => (
              <li key={job.id}>
                <JobCard job={job} />
                {reasons.length > 0 && (
                  <p className="mt-1 px-1 text-xs text-muted-foreground">Why: {reasons.join(" · ")}</p>
                )}
              </li>
            ))}
          </ul>
          <div className="mt-6 flex justify-center">
            {query.hasNextPage ? (
              <Button variant="outline" onClick={() => query.fetchNextPage()} disabled={query.isFetchingNextPage}>
                {query.isFetchingNextPage && <Loader2 className="animate-spin" />} Load more
              </Button>
            ) : (
              <p className="text-sm text-muted-foreground">That&apos;s your top {items.length}.</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
