"use client";

import { ArrowLeft, Building2, CalendarDays, ExternalLink, MapPin } from "lucide-react";
import Link from "next/link";

import { HiringBadge, levelLabel, postedAgo, SaveButton, workModeLabel } from "@/components/jobs/job-card";
import { remoteLabel } from "@/components/jobs/location-filters";
import { MatchCard, PrepareCard, SkillGapCoach } from "@/components/matching/match-panel";
import { ReportProblem } from "@/components/report-problem";
import { TrackButton } from "@/components/tracker/track-button";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, Skeleton } from "@/components/ui/primitives";
import { useJob } from "@/lib/api/jobs";

export function JobDetailView({ jobId }: { jobId: string }) {
  const { data: job, isPending, isError, error, refetch } = useJob(jobId);

  if (isPending) return <Skeleton className="mx-auto h-[32rem] max-w-5xl rounded-xl" />;
  if (isError)
    return (
      <Card className="mx-auto max-w-5xl">
        <ErrorState error={error} onRetry={() => refetch()} />
      </Card>
    );

  const mode = remoteLabel(job) ?? workModeLabel(job.work_mode);
  const level = levelLabel(job.experience_level);
  return (
    <div className="mx-auto max-w-5xl">
      <Button asChild variant="ghost" size="sm" className="mb-4">
        <Link href="/jobs">
          <ArrowLeft /> Back to jobs
        </Link>
      </Button>

      <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
        <article className="min-w-0">
          <header className="rounded-xl border bg-card p-5 sm:p-6">
            <h1 className="text-2xl font-semibold sm:text-3xl">{job.title}</h1>
            <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <Building2 className="size-4" aria-hidden /> {job.company_name}
              </span>
              {job.location && (
                <span className="inline-flex items-center gap-1.5">
                  <MapPin className="size-4" aria-hidden /> {job.location}
                </span>
              )}
              <span className="inline-flex items-center gap-1.5">
                <CalendarDays className="size-4" aria-hidden /> Posted{" "}
                {postedAgo(job.posted_at ?? job.first_seen_at)}
              </span>
            </p>
            <div className="mt-4 flex flex-wrap gap-1.5">
              <HiringBadge job={job} />
              {mode && <Badge>{mode}</Badge>}
              {level && <Badge variant="outline">{level}</Badge>}
              {job.employment_type && <Badge variant="outline">{job.employment_type}</Badge>}
              {job.department && <Badge variant="muted">{job.department}</Badge>}
              {job.salary && <Badge variant="success">{job.salary}</Badge>}
            </div>
            {!job.is_active && (
              <p role="status" className="mt-4 rounded-lg bg-warning/10 p-3 text-sm">
                This job is no longer listed on the company&apos;s site. It may have been filled.
              </p>
            )}
            <div className="mt-5 flex flex-wrap gap-2">
              <Button asChild variant="sunrise" size="lg">
                <a href={job.apply_url} target="_blank" rel="noopener noreferrer nofollow">
                  Apply on company site <ExternalLink />
                </a>
              </Button>
              <SaveButton job={job} size="default" />
              <TrackButton jobId={job.id} />
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              {job.attribution && <p className="text-xs text-muted-foreground">{job.attribution}</p>}
              <ReportProblem kind="broken_job_link" targetType="job" targetId={job.id} />
            </div>
          </header>

          <SkillGapCoach jobId={job.id} />

          <section aria-label="Job description" className="mt-6 rounded-xl border bg-card p-5 sm:p-6">
            {/* Sanitised on the server with an allow-list (nh3): formatting only, no scripts. */}
            <div className="job-description" dangerouslySetInnerHTML={{ __html: job.description_html }} />
          </section>
        </article>

        <aside className="space-y-4">
          <MatchCard jobId={job.id} />
          {job.skills.length > 0 && !job.match && (
            <Card>
              <CardHeader>
                <CardTitle>Skills mentioned</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-1.5">
                {job.skills.map((s) => (
                  <Badge key={s} variant="muted">
                    {s}
                  </Badge>
                ))}
              </CardContent>
            </Card>
          )}
          <PrepareCard jobId={job.id} />
        </aside>
      </div>
    </div>
  );
}
