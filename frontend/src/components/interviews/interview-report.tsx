"use client";

import { ArrowLeft, ArrowRight, CheckCircle2, Loader2, Quote, RefreshCw, Target, TrendingUp } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { ScoreRing } from "@/components/matching/match-badge";
import { PageHeader } from "@/components/page-header";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, Skeleton } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api/client";
import { isReportWorking, useReport, useRetryReport } from "@/lib/api/interviews";
import type { ReportResult } from "@/lib/api/types";

function List({ title, items, icon }: { title: string; items: string[]; icon: React.ReactNode }) {
  if (!items.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {icon} {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export function ReportBody({ result }: { result: ReportResult }) {
  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-6 pt-5">
          <ScoreRing score={result.overall_score} size={112} />
          <div className="min-w-0 flex-1">
            <p className="text-lg leading-relaxed">{result.summary}</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Answered {result.answered} of {result.total_questions} question
              {result.total_questions === 1 ? "" : "s"}
              {result.hints_used > 0 && ` · ${result.hints_used} hint${result.hints_used === 1 ? "" : "s"} used`}
              {result.rubric_score !== null && result.rubric_score !== undefined &&
                ` · rubric ${result.rubric_score}/100, answers ${result.questions_score}/100`}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Rubric</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {result.criteria.map((c) => (
            <div key={c.key}>
              <div className="flex justify-between text-sm">
                <span className="font-medium">{c.name}</span>
                <span className="text-muted-foreground">{c.score ? `${c.score}/5` : "not judged"}</span>
              </div>
              <div
                className="mt-1 h-2 overflow-hidden rounded-full bg-muted"
                role="meter"
                aria-label={c.name}
                aria-valuemin={0}
                aria-valuemax={5}
                aria-valuenow={c.score ?? 0}
              >
                <div className="h-full rounded-full bg-primary" style={{ width: `${((c.score ?? 0) / 5) * 100}%` }} />
              </div>
              {c.comment && <p className="mt-1 text-sm text-muted-foreground">{c.comment}</p>}
              {c.evidence && (
                <p className="mt-1 flex gap-1.5 text-sm italic">
                  <Quote className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                  {c.evidence}
                </p>
              )}
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Question by question</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-4">
            {result.questions.map((q) => (
              <li key={q.index} className="rounded-lg border p-4">
                <div className="flex items-start justify-between gap-3">
                  <p className="font-medium">
                    {q.index + 1}. {q.prompt}
                  </p>
                  <Badge variant={q.answered ? (q.score >= 7 ? "success" : "default") : "muted"}>
                    {q.answered ? `${q.score}/10` : "Not answered"}
                  </Badge>
                </div>
                {q.feedback && <p className="mt-2 text-sm text-muted-foreground">{q.feedback}</p>}
                {(q.strengths?.length ?? 0) + (q.improvements?.length ?? 0) > 0 && (
                  <div className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
                    {(q.strengths ?? []).map((s) => (
                      <p key={s} className="flex gap-1.5">
                        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden /> {s}
                      </p>
                    ))}
                    {(q.improvements ?? []).map((s) => (
                      <p key={s} className="flex gap-1.5">
                        <TrendingUp className="mt-0.5 size-4 shrink-0 text-sunrise" aria-hidden /> {s}
                      </p>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        <List title="Strengths" items={result.strengths} icon={<CheckCircle2 className="size-4 text-success" />} />
        <List title="To work on" items={result.weaknesses} icon={<Target className="size-4 text-sunrise" />} />
        <List title="Tips" items={result.tips} icon={<TrendingUp className="size-4 text-primary" />} />
      </div>

      {result.next_practice && (
        <Card className="flex flex-wrap items-center gap-4 p-5">
          <div className="min-w-0 flex-1">
            <p className="text-sm text-muted-foreground">Suggested next practice</p>
            <p className="font-semibold">{result.next_practice.focus}</p>
            {result.next_practice.reason && (
              <p className="text-sm text-muted-foreground">{result.next_practice.reason}</p>
            )}
          </div>
          <Button asChild variant="sunrise">
            <Link href="/interviews">
              Practise again <ArrowRight />
            </Link>
          </Button>
        </Card>
      )}
    </div>
  );
}

export function InterviewReportView({ interviewId }: { interviewId: string }) {
  const report = useReport(interviewId);
  const retry = useRetryReport(interviewId);
  const data = report.data;

  return (
    <div className="mx-auto max-w-4xl">
      <Button asChild variant="ghost" size="sm" className="mb-4">
        <Link href="/interviews">
          <ArrowLeft /> All interviews
        </Link>
      </Button>
      <PageHeader
        title={data ? `${data.interview.type_name} interview report` : "Interview report"}
        description={
          data?.interview.job_title
            ? `${data.interview.job_title} at ${data.interview.company_name}`
            : "How you did, and what to practise next."
        }
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href={`/interviews/${interviewId}`}>Transcript</Link>
          </Button>
        }
      />
      {report.isError ? (
        <Card>
          <ErrorState error={report.error} onRetry={() => report.refetch()} />
        </Card>
      ) : !data ? (
        <Skeleton className="h-96 w-full rounded-xl" />
      ) : isReportWorking(data.status) ? (
        <Card className="p-8 text-center" role="status">
          <Loader2 className="mx-auto size-8 animate-spin text-primary" aria-hidden />
          <p className="mt-4 font-medium">Writing your feedback…</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Reviewing every answer against the rubric. This usually takes a minute or two.
          </p>
        </Card>
      ) : data.status === "skipped" ? (
        <Card className="p-8 text-center">
          <p className="font-medium">No answers to review</p>
          <p className="mt-1 text-sm text-muted-foreground">
            This interview ended before any question was answered, so there&apos;s no score.
          </p>
          <Button asChild className="mt-4" variant="sunrise">
            <Link href="/interviews">Start another</Link>
          </Button>
        </Card>
      ) : data.status === "failed" || !data.result ? (
        <Card className="p-8 text-center">
          <p role="alert" className="font-medium">
            {data.error ?? "The report couldn't be written."}
          </p>
          <Button
            className="mt-4"
            onClick={() => retry.mutate(undefined, { onError: (e) => toast.error(errorMessage(e)) })}
            disabled={retry.isPending}
          >
            <RefreshCw /> Try again
          </Button>
        </Card>
      ) : (
        <>
          <ReportBody result={data.result} />
          <p className="mt-4 text-xs text-muted-foreground">
            AI-generated by {data.generated_by}. Scores are combined by GlideUp from the rubric and
            per-question marks; quotes are checked against what you actually said.
          </p>
        </>
      )}
    </div>
  );
}
