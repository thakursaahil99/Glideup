"use client";

import { ArrowRight, Code2, FileUp, Loader2, MessagesSquare, RefreshCw, Sparkles } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { postedAgo } from "@/components/jobs/job-card";
import { ScoreRing } from "@/components/matching/match-badge";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, Skeleton } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api/client";
import { useJobMatch, useStartAnalysis } from "@/lib/api/matches";
import type { MatchDetail } from "@/lib/api/types";

const SOURCE_LABEL: Record<string, string> = { resume: "resume", github: "GitHub", website: "portfolio" };

const PARTS: { key: keyof NonNullable<MatchDetail["parts"]>; label: string; hint: string }[] = [
  { key: "semantic", label: "Role fit", hint: "How closely your experience reads like this job" },
  { key: "skills", label: "Skills", hint: "Share of the job's skills you have" },
  { key: "level", label: "Experience level", hint: "Your years against what this level usually asks" },
];

function PartBar({ label, hint, value }: { label: string; hint: string; value: number | null }) {
  return (
    <div title={hint}>
      <div className="flex justify-between text-sm">
        <span>{label}</span>
        <span className="text-muted-foreground">{value === null ? "—" : `${value}%`}</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary" style={{ width: `${value ?? 0}%` }} />
      </div>
    </div>
  );
}

function NeedsResume() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>See how well you fit</CardTitle>
        <CardDescription>
          Upload your resume and we&apos;ll score every job against your skills and experience.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button asChild variant="sunrise" className="w-full">
          <Link href="/onboarding">
            <FileUp /> Upload resume
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

/** Sidebar card: score, what it is made of, and the skill comparison. */
export function MatchCard({ jobId }: { jobId: string }) {
  const { data: match, isPending, isError, error, refetch } = useJobMatch(jobId);
  if (isPending) return <Skeleton className="h-72 w-full rounded-xl" />;
  if (isError)
    return (
      <Card>
        <ErrorState error={error} onRetry={() => refetch()} />
      </Card>
    );
  if (!match.available) return <NeedsResume />;

  const summary = match.summary;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Your match</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {summary ? (
          <div className="flex items-center gap-4">
            <ScoreRing score={summary.score} />
            <div>
              <p className="font-semibold">{summary.label}</p>
              {summary.partial && (
                <p className="mt-1 text-xs text-muted-foreground">
                  {match.embedding_pending
                    ? "Based on skills for now; the full score appears in a moment."
                    : "Based on skills only."}
                </p>
              )}
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            This posting doesn&apos;t list skills we can compare yet.
          </p>
        )}

        {match.parts && (
          <div className="space-y-3">
            {PARTS.map((part) => (
              <PartBar key={part.key} label={part.label} hint={part.hint} value={match.parts?.[part.key] ?? null} />
            ))}
          </div>
        )}

        {match.matched.length > 0 && (
          <section aria-label="Skills you have">
            <h3 className="mb-1.5 text-sm font-medium">You have</h3>
            <ul className="flex flex-wrap gap-1.5">
              {match.matched.map((skill) => (
                <li key={skill.name}>
                  <Badge
                    variant="success"
                    title={`From your ${skill.sources.map((s) => SOURCE_LABEL[s] ?? s).join(" and ")}`}
                  >
                    {skill.name}
                  </Badge>
                </li>
              ))}
            </ul>
          </section>
        )}
        {match.transferable.length > 0 && (
          <section aria-label="Close to what you know">
            <h3 className="mb-1.5 text-sm font-medium">Close to what you know</h3>
            <ul className="flex flex-wrap gap-1.5">
              {match.transferable.map((t) => (
                <li key={t.skill}>
                  <Badge variant="default" title={`You know ${t.via}, which is closely related`}>
                    {t.skill} ← {t.via}
                  </Badge>
                </li>
              ))}
            </ul>
          </section>
        )}
        {match.missing.length > 0 && (
          <section aria-label="Missing skills">
            <h3 className="mb-1.5 text-sm font-medium">Missing</h3>
            <ul className="flex flex-wrap gap-1.5">
              {match.missing.map((skill) => (
                <li key={skill}>
                  <Badge variant="destructive">{skill}</Badge>
                </li>
              ))}
            </ul>
          </section>
        )}
      </CardContent>
    </Card>
  );
}

/** Main-column section: the AI coach's explanation of the gaps, on demand. */
export function SkillGapCoach({ jobId }: { jobId: string }) {
  const { data: match } = useJobMatch(jobId);
  const start = useStartAnalysis(jobId);
  if (!match?.available) return null;

  const analysis = match.analysis;
  const { strengths = [], missing = [], weak = [] } = analysis?.result ?? {};
  const working = analysis?.status === "pending" || analysis?.status === "analyzing" || start.isPending;
  const run = () => start.mutate(undefined, { onError: (e) => toast.error(errorMessage(e)) });

  return (
    <section aria-labelledby="coach-heading" className="mt-6 rounded-xl border bg-card p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="coach-heading" className="flex items-center gap-2 text-lg font-semibold">
            <Sparkles className="size-5 text-sunrise" aria-hidden /> Skill gap coach
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            What stands between you and this role, with a concrete way to close each gap.
          </p>
        </div>
        {analysis?.status === "done" && analysis.stale && (
          <Button variant="outline" size="sm" onClick={run} disabled={working}>
            <RefreshCw /> Refresh
          </Button>
        )}
      </div>

      {working ? (
        <p role="status" className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden /> Reading the job and your profile… this
          usually takes under a minute.
        </p>
      ) : !analysis ? (
        <Button className="mt-4" variant="sunrise" onClick={run}>
          <Sparkles /> Analyze my gaps
        </Button>
      ) : analysis.status === "failed" ? (
        <div className="mt-4 space-y-3">
          <p role="alert" className="text-sm text-destructive">
            {analysis.error ?? "The analysis failed."}
          </p>
          <Button variant="outline" size="sm" onClick={run}>
            <RefreshCw /> Try again
          </Button>
        </div>
      ) : analysis.result ? (
        <div className="mt-4 space-y-5">
          {analysis.stale && (
            <p className="rounded-lg bg-warning/10 p-3 text-sm">
              Your profile or this job changed since this analysis. Refresh for an up-to-date one.
            </p>
          )}
          <p>{analysis.result.summary}</p>
          {strengths.length > 0 && (
            <div>
              <h3 className="mb-1.5 text-sm font-medium">Where you fit</h3>
              <ul className="flex flex-wrap gap-1.5">
                {strengths.map((s) => (
                  <li key={s}>
                    <Badge variant="success">{s}</Badge>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {missing.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium">Gaps to close</h3>
              <ul className="space-y-3">
                {missing.map((gap) => (
                  <li key={gap.skill} className="rounded-lg border p-3">
                    <p className="flex flex-wrap items-center gap-2 font-medium">
                      {gap.skill}
                      <Badge variant={gap.importance === "required" ? "destructive" : "outline"}>
                        {gap.importance === "required" ? "Required" : "Nice to have"}
                      </Badge>
                    </p>
                    {gap.reason && <p className="mt-1 text-sm text-muted-foreground">{gap.reason}</p>}
                    {gap.suggestion && (
                      <p className="mt-1 flex gap-1.5 text-sm">
                        <ArrowRight className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                        {gap.suggestion}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {weak.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium">Worth strengthening</h3>
              <ul className="space-y-3">
                {weak.map((gap) => (
                  <li key={gap.skill} className="rounded-lg border p-3">
                    <p className="font-medium">{gap.skill}</p>
                    {gap.reason && <p className="mt-1 text-sm text-muted-foreground">{gap.reason}</p>}
                    {gap.suggestion && (
                      <p className="mt-1 flex gap-1.5 text-sm">
                        <ArrowRight className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                        {gap.suggestion}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            AI-generated{analysis.analyzed_at && <>, {postedAgo(analysis.analyzed_at)}</>}. Skills it
            mentions are checked against the posting and your profile.
          </p>
        </div>
      ) : null}
    </section>
  );
}

/** One-click practice for this job; the tools themselves ship in phases 5 and 6. */
export function PrepareCard({ jobId }: { jobId: string }) {
  const { data: match } = useJobMatch(jobId);
  const stack = [...(match?.practice.languages ?? []), ...(match?.practice.frameworks ?? [])];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Prepare for this job</CardTitle>
        <CardDescription>Practice tailored to this posting is coming soon.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <Button variant="outline" className="w-full justify-start" disabled title="Coming in phase 5">
          <MessagesSquare /> Practice interview for this job
        </Button>
        <Button variant="outline" className="h-auto w-full justify-start py-2" disabled title="Coming in phase 6">
          <Code2 />
          <span className="text-left">
            Take a skill test
            {stack.length > 0 && (
              <span className="block text-xs text-muted-foreground">{stack.join(", ")}</span>
            )}
          </span>
        </Button>
      </CardContent>
    </Card>
  );
}
