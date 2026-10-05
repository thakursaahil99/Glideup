"use client";

import { ArrowLeft, CheckCircle2, Clock, Loader2, RefreshCw, Send, XCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { toast } from "sonner";

import { formatClock } from "@/components/interviews/interview-room";
import { ScoreRing } from "@/components/matching/match-badge";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { Badge, Skeleton, Textarea } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api/client";
import { useAttempt, useSaveAnswers, useSubmitAttempt } from "@/lib/api/skills";
import type { AttemptQuestion, FrameworkAttempt } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type Answers = Record<string, number | string | null>;
const SECTION_LABELS: Record<string, string> = {
  mcq: "Multiple choice",
  review: "Code review",
  viva: "Viva",
  project: "Mini-project",
};
const AUTOSAVE_MS = 1500;

export function answeredCount(questions: AttemptQuestion[], answers: Answers): number {
  return questions.filter((q) => {
    const a = answers[q.id];
    return typeof a === "number" || (typeof a === "string" && a.trim().length > 0);
  }).length;
}

function QuestionInput({
  question,
  value,
  onChange,
  disabled,
}: {
  question: AttemptQuestion;
  value: number | string | null | undefined;
  onChange: (value: number | string) => void;
  disabled: boolean;
}) {
  const content = question.content as {
    options?: string[];
    code?: string;
    starter?: string;
    requirements?: string[];
  };
  if (question.type === "mcq") {
    return (
      <fieldset className="space-y-2" disabled={disabled}>
        <legend className="sr-only">{question.title}</legend>
        {(content.options ?? []).map((option, i) => (
          <label
            key={i}
            className={cn(
              "flex cursor-pointer items-start gap-2 rounded-lg border p-3 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
              value === i && "border-primary bg-primary-soft",
            )}
          >
            <input
              type="radio"
              name={question.id}
              className="mt-0.5"
              checked={value === i}
              onChange={() => onChange(i)}
            />
            {option}
          </label>
        ))}
      </fieldset>
    );
  }
  return (
    <div className="space-y-2">
      {content.code && (
        <pre className="max-h-80 overflow-auto rounded-lg bg-muted p-3 text-xs">{content.code}</pre>
      )}
      {content.requirements && (
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          {content.requirements.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      <Textarea
        aria-label={`Answer: ${question.title}`}
        disabled={disabled}
        value={
          typeof value === "string" ? value : ((question.type === "project" ? content.starter : "") ?? "")
        }
        onChange={(e) => onChange(e.target.value)}
        spellCheck={question.type !== "project"}
        className={cn("min-h-40", question.type === "project" && "min-h-64 font-mono text-sm")}
        placeholder={
          question.type === "review"
            ? "List each problem you see and how you'd fix it."
            : question.type === "viva"
              ? "Explain in your own words."
              : undefined
        }
      />
    </div>
  );
}

function Results({ attempt }: { attempt: FrameworkAttempt }) {
  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-center gap-6 p-5">
        <ScoreRing score={attempt.score ?? 0} size={112} />
        <div className="min-w-0 flex-1">
          <p className="text-xl font-semibold capitalize">{attempt.level}</p>
          <p className="text-sm text-muted-foreground">{attempt.framework_name} skill level</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {Object.entries(attempt.sections).map(([section, score]) => (
              <div key={section}>
                <div className="flex justify-between text-sm">
                  <span>{SECTION_LABELS[section] ?? section}</span>
                  <span className="text-muted-foreground">{String(score)}%</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-muted">
                  <div className="h-full rounded-full bg-primary" style={{ width: `${Number(score)}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </Card>
      {attempt.questions.map((q, n) => {
        const result = q.result as {
          score?: number;
          feedback?: string;
          items?: { key: string; description?: string; credit?: number }[];
        } | null;
        const content = q.content as { options?: string[]; answer?: number; explanation?: string };
        const score = Math.round((result?.score ?? 0) * 100);
        return (
          <Card key={q.id} className="space-y-2 p-4">
            <p className="flex items-start gap-2 font-medium">
              {score >= 50 ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
              ) : (
                <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
              )}
              <span className="flex-1">
                {n + 1}. {q.title}
              </span>
              <Badge variant="muted">{SECTION_LABELS[q.type]}</Badge>
              <Badge variant={score >= 50 ? "success" : "destructive"}>{score}%</Badge>
            </p>
            {q.type === "mcq" && content.options && typeof content.answer === "number" && (
              <p className="text-sm">
                Correct answer: <span className="font-medium">{content.options[content.answer]}</span>
              </p>
            )}
            {(content.explanation || result?.feedback) && (
              <p className="text-sm text-muted-foreground">{content.explanation || result?.feedback}</p>
            )}
            {q.type !== "mcq" && result?.items && (
              <ul className="space-y-1 text-sm">
                {result.items.map((item) => (
                  <li key={item.key} className="flex gap-2">
                    <span aria-hidden>{item.credit === 1 ? "✓" : item.credit ? "½" : "✗"}</span>
                    <span className={cn(!item.credit && "text-muted-foreground")}>{item.description}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        );
      })}
    </div>
  );
}

function Taking({ attempt }: { attempt: FrameworkAttempt }) {
  const [answers, setAnswers] = useState<Answers>(attempt.answers as Answers);
  const [confirm, setConfirm] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const save = useSaveAnswers(attempt.id);
  const submit = useSubmitAttempt(attempt.id);
  const pending = useRef<Answers>({});
  const timer = useRef<number | undefined>(undefined);
  const secondsLeft = (new Date(attempt.ends_at).getTime() - now) / 1000;
  const answered = answeredCount(attempt.questions, answers);

  useEffect(() => {
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(tick);
  }, []);

  function flush() {
    const batch = pending.current;
    pending.current = {};
    if (Object.keys(batch).length) save.mutate(batch, { onError: (e) => toast.error(errorMessage(e)) });
  }

  function update(id: string, value: number | string) {
    setAnswers((current) => ({ ...current, [id]: value }));
    pending.current[id] = value;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(flush, AUTOSAVE_MS);
  }

  function finish() {
    window.clearTimeout(timer.current);
    const batch = pending.current;
    pending.current = {};
    const doSubmit = () => submit.mutate(undefined, { onError: (e) => toast.error(errorMessage(e)) });
    if (Object.keys(batch).length) save.mutate(batch, { onSettled: doSubmit });
    else doSubmit();
  }

  return (
    <>
      <div className="sticky top-16 z-10 mb-4 flex flex-wrap items-center gap-3 rounded-xl border bg-card/95 p-3 backdrop-blur">
        <Badge variant={secondsLeft < 300 ? "sunrise" : "outline"} className="px-3 py-1 text-sm tabular-nums">
          <Clock className="size-4" aria-hidden /> {secondsLeft > 0 ? formatClock(secondsLeft) : "Time's up"}
        </Badge>
        <span className="text-sm text-muted-foreground">
          {answered} of {attempt.questions.length} answered
          {save.isPending ? " · saving…" : ""}
        </span>
        <Button
          className="ml-auto"
          variant="sunrise"
          size="sm"
          onClick={() => setConfirm(true)}
          disabled={submit.isPending}
        >
          <Send /> Submit test
        </Button>
      </div>
      <ol className="space-y-4">
        {attempt.questions.map((q, n) => (
          <li key={q.id}>
            <Card className="space-y-3 p-4">
              <p className="flex items-start gap-2">
                <span className="font-medium">
                  {n + 1}. {q.type === "mcq" ? q.statement : q.title}
                </span>
                <Badge variant="muted" className="ml-auto">
                  {SECTION_LABELS[q.type]}
                </Badge>
              </p>
              {q.type !== "mcq" && (
                <div className="text-sm [&_code]:rounded [&_code]:bg-muted [&_code]:px-1">
                  <Markdown>{q.statement}</Markdown>
                </div>
              )}
              <QuestionInput
                question={q}
                value={answers[q.id]}
                onChange={(v) => update(q.id, v)}
                disabled={secondsLeft < -120}
              />
            </Card>
          </li>
        ))}
      </ol>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogTitle>Submit your test?</DialogTitle>
          <DialogDescription>
            You answered {answered} of {attempt.questions.length}. Unanswered questions score 0.
          </DialogDescription>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(false)}>
              Keep working
            </Button>
            <Button
              variant="sunrise"
              onClick={() => {
                setConfirm(false);
                finish();
              }}
            >
              Submit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function AttemptView({ attemptId }: { attemptId: string }) {
  const attempt = useAttempt(attemptId);
  const submit = useSubmitAttempt(attemptId);
  if (attempt.isPending) return <Skeleton className="mx-auto h-[70dvh] max-w-3xl rounded-xl" />;
  if (attempt.isError)
    return (
      <Card className="mx-auto max-w-xl">
        <ErrorState error={attempt.error} onRetry={() => attempt.refetch()} />
      </Card>
    );
  const data = attempt.data;
  return (
    <div className="mx-auto max-w-3xl">
      <Button asChild variant="ghost" size="sm" className="mb-3">
        <Link href="/tests">
          <ArrowLeft /> All tests
        </Link>
      </Button>
      <h1 className="mb-4 text-2xl font-semibold">{data.framework_name} test</h1>
      {data.status === "in_progress" ? (
        <Taking key={data.id} attempt={data} />
      ) : data.status === "grading" ? (
        <Card className="p-8 text-center" role="status">
          <Loader2 className="mx-auto size-8 animate-spin text-primary" aria-hidden />
          <p className="mt-4 font-medium">Grading your answers…</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Reviews, viva answers and code are checked one by one.
          </p>
        </Card>
      ) : data.status === "failed" ? (
        <Card className="p-8 text-center">
          <p role="alert" className="font-medium">
            {data.error ?? "Grading failed."}
          </p>
          <Button className="mt-4" onClick={() => submit.mutate()} disabled={submit.isPending}>
            <RefreshCw /> Try again
          </Button>
        </Card>
      ) : (
        <Results attempt={data} />
      )}
    </div>
  );
}
