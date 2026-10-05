"use client";

import { ArrowRight, BriefcaseBusiness, Clock, ListChecks, Loader2, MessagesSquare } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { postedAgo } from "@/components/jobs/job-card";
import { MatchBadge } from "@/components/matching/match-badge";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge, Skeleton } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api/client";
import { useCreateInterview, useInterviews, useInterviewTypes } from "@/lib/api/interviews";
import { useJob } from "@/lib/api/jobs";
import { DIFFICULTIES, type Difficulty, type InterviewSummary } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export function statusLabel(item: Pick<InterviewSummary, "status" | "report_status">): string {
  if (item.status === "preparing") return "Preparing";
  if (item.status === "ready") return "Not started";
  if (item.status === "in_progress") return "In progress";
  if (item.status === "failed") return "Couldn't prepare";
  if (item.report_status === "done") return "Report ready";
  if (item.report_status === "skipped") return "No answers";
  if (item.report_status === "failed") return "Report failed";
  return "Writing report";
}

function JobBanner({ jobId }: { jobId: string }) {
  const { data: job } = useJob(jobId);
  if (!job) return <Skeleton className="mb-6 h-20 w-full rounded-xl" />;
  return (
    <Card className="mb-6 flex flex-wrap items-center gap-3 p-4">
      <BriefcaseBusiness className="size-5 text-primary" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm text-muted-foreground">Practising for</p>
        <p className="font-medium">
          {job.title} · {job.company_name}
        </p>
      </div>
      {job.match && <MatchBadge match={job.match} />}
    </Card>
  );
}

export function InterviewsHome() {
  const router = useRouter();
  const params = useSearchParams();
  const jobId = params.get("job");
  const types = useInterviewTypes();
  const history = useInterviews();
  const create = useCreateInterview();
  const available = (types.data ?? []).filter((t) => (jobId ? true : t.key !== "job_specific"));
  const [picked, setPicked] = useState<string | null>(jobId ? "job_specific" : null);
  const [difficulty, setDifficulty] = useState<Difficulty | null>(null);
  const selected = available.find((t) => t.key === picked) ?? null;

  function begin() {
    if (!selected) return;
    create.mutate(
      {
        type_key: selected.key,
        difficulty: difficulty ?? selected.difficulty,
        job_id: selected.key === "job_specific" && jobId ? jobId : undefined,
      },
      {
        onSuccess: (detail) => router.push(`/interviews/${detail.interview.id}`),
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Mock interviews"
        description="Practise with an AI interviewer that asks follow-ups, keeps time and writes you a feedback report."
      />
      {jobId && <JobBanner jobId={jobId} />}

      <section aria-labelledby="new-heading">
        <h2 id="new-heading" className="mb-3 text-lg font-semibold">
          Start a new interview
        </h2>
        {types.isError ? (
          <Card>
            <ErrorState error={types.error} onRetry={() => types.refetch()} />
          </Card>
        ) : types.isPending ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-32 rounded-xl" />
            ))}
          </div>
        ) : (
          <div role="radiogroup" aria-label="Interview type" className="grid gap-3 sm:grid-cols-2">
            {available.map((type) => (
              <button
                key={type.key}
                type="button"
                role="radio"
                aria-checked={picked === type.key}
                onClick={() => setPicked(type.key)}
                className={cn(
                  "rounded-xl border bg-card p-4 text-left transition-colors hover:border-primary/50",
                  picked === type.key && "border-primary ring-2 ring-primary/20",
                )}
              >
                <p className="font-semibold">{type.name}</p>
                <p className="mt-1 text-sm text-muted-foreground">{type.description}</p>
                <p className="mt-3 flex gap-4 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <Clock className="size-3.5" aria-hidden /> {type.duration_minutes} min
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <ListChecks className="size-3.5" aria-hidden /> {type.question_count} question
                    {type.question_count === 1 ? "" : "s"}
                  </span>
                </p>
              </button>
            ))}
          </div>
        )}

        {selected && (
          <Card className="mt-4 flex flex-wrap items-center gap-4 p-4">
            <fieldset className="flex items-center gap-2">
              <legend className="sr-only">Difficulty</legend>
              <span className="text-sm font-medium">Difficulty</span>
              {DIFFICULTIES.map((d) => {
                const active = (difficulty ?? selected.difficulty) === d.value;
                return (
                  <label
                    key={d.value}
                    className={cn(
                      "cursor-pointer rounded-full border px-3 py-1 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                      active ? "border-primary bg-primary-soft text-primary" : "hover:bg-accent",
                    )}
                  >
                    <input
                      type="radio"
                      name="difficulty"
                      className="sr-only"
                      checked={active}
                      onChange={() => setDifficulty(d.value)}
                    />
                    {d.label}
                  </label>
                );
              })}
            </fieldset>
            <Button variant="sunrise" className="ml-auto" onClick={begin} disabled={create.isPending}>
              {create.isPending ? <Loader2 className="animate-spin" /> : <MessagesSquare />}
              Set up interview
            </Button>
          </Card>
        )}
        {!jobId && (
          <p className="mt-3 text-sm text-muted-foreground">
            Want questions written from a real job? Open a job and choose{" "}
            <span className="font-medium">Practice interview for this job</span>.
          </p>
        )}
      </section>

      <section aria-labelledby="history-heading" className="mt-10">
        <h2 id="history-heading" className="mb-3 text-lg font-semibold">
          Your interviews
        </h2>
        {history.isError ? (
          <Card>
            <ErrorState error={history.error} onRetry={() => history.refetch()} />
          </Card>
        ) : history.isPending ? (
          <Skeleton className="h-40 w-full rounded-xl" />
        ) : history.data.length === 0 ? (
          <Card>
            <EmptyState
              icon={<MessagesSquare className="size-5" aria-hidden />}
              title="No interviews yet"
              body="Your interviews and their reports will appear here."
            />
          </Card>
        ) : (
          <Card>
            <ul className="divide-y">
              {history.data.map((item) => {
                const href =
                  item.report_status === "done"
                    ? `/interviews/${item.id}/report`
                    : `/interviews/${item.id}`;
                return (
                  <li key={item.id} className="flex flex-wrap items-center gap-3 p-4">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">
                        {item.type_name}
                        {item.job_title && (
                          <span className="font-normal text-muted-foreground">
                            {" "}
                            · {item.job_title} at {item.company_name}
                          </span>
                        )}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {postedAgo(item.created_at)} · {item.difficulty}
                      </p>
                    </div>
                    {item.overall_score !== null && item.overall_score !== undefined ? (
                      <Badge variant="success">{item.overall_score}/100</Badge>
                    ) : (
                      <Badge variant="muted">{statusLabel(item)}</Badge>
                    )}
                    <Button asChild variant="ghost" size="sm">
                      <Link href={href}>
                        {item.report_status === "done" ? "Report" : "Open"} <ArrowRight />
                      </Link>
                    </Button>
                  </li>
                );
              })}
            </ul>
          </Card>
        )}
      </section>
    </div>
  );
}
