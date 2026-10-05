"use client";

import { ArrowLeft, CheckCircle2, Loader2, Play, RotateCcw, Send, XCircle } from "lucide-react";
import Link from "next/link";
import { useState, type KeyboardEvent } from "react";
import Markdown from "react-markdown";
import { toast } from "sonner";

import { DIFFICULTY_VARIANT } from "@/components/tests/problems-list";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge, NativeSelect, Skeleton } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api/client";
import {
  isPending,
  useMySubmissions,
  useProblem,
  useRunCode,
  useSubmission,
  useSubmitCode,
} from "@/lib/api/problems";
import { type CaseResult, type ProblemDetail, VERDICT_LABELS, type Verdict } from "@/lib/api/types";
import { cn, formatDateTime } from "@/lib/utils";

const DRAFT_KEY = (slug: string, lang: string) => `glideup:code:${slug}:${lang}`;

function readDraft(slug: string, lang: string): string | null {
  try {
    return window.localStorage.getItem(DRAFT_KEY(slug, lang));
  } catch {
    return null;
  }
}

function saveDraft(slug: string, lang: string, code: string) {
  try {
    window.localStorage.setItem(DRAFT_KEY(slug, lang), code);
  } catch {
    // storage may be unavailable (private mode); drafts are a convenience only
  }
}

/** Tab inserts indentation instead of leaving the editor. */
export function handleEditorKey(event: KeyboardEvent<HTMLTextAreaElement>, setCode: (code: string) => void) {
  if (event.key !== "Tab" || event.shiftKey) return;
  event.preventDefault();
  const el = event.currentTarget;
  const { selectionStart: start, selectionEnd: end, value } = el;
  const next = `${value.slice(0, start)}    ${value.slice(end)}`;
  setCode(next);
  requestAnimationFrame(() => el.setSelectionRange(start + 4, start + 4));
}

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const variant =
    verdict === "accepted"
      ? "success"
      : verdict === "queued" || verdict === "running"
        ? "muted"
        : "destructive";
  return <Badge variant={variant}>{VERDICT_LABELS[verdict]}</Badge>;
}

function Results({
  verdict,
  passed,
  total,
  results,
  compileOutput,
}: {
  verdict: Verdict;
  passed: number;
  total: number;
  results: CaseResult[];
  compileOutput?: string | null;
}) {
  return (
    <div className="space-y-3" aria-live="polite">
      <p className="flex items-center gap-2 font-medium">
        <VerdictBadge verdict={verdict} />
        {!isPending(verdict) && `${passed} / ${total} tests passed`}
      </p>
      {compileOutput && (
        <pre className="max-h-48 overflow-auto rounded-lg bg-destructive/10 p-3 text-xs text-destructive">
          {compileOutput}
        </pre>
      )}
      <ul className="space-y-2">
        {results.map((r) => (
          <li key={r.position} className="rounded-lg border p-3 text-sm">
            <p className="flex items-center gap-2">
              {r.verdict === "accepted" ? (
                <CheckCircle2 className="size-4 text-success" aria-hidden />
              ) : (
                <XCircle className="size-4 text-destructive" aria-hidden />
              )}
              Test {r.position + 1}
              {r.hidden && <span className="text-muted-foreground">(hidden)</span>}
              <span className="ml-auto text-xs text-muted-foreground">
                {VERDICT_LABELS[r.verdict]}
                {r.time_ms != null && ` · ${r.time_ms} ms`}
              </span>
            </p>
            {!r.hidden && r.verdict !== "accepted" && (
              <div className="mt-2 grid gap-2 sm:grid-cols-3">
                {(
                  [
                    ["Input", r.input],
                    ["Expected", r.expected],
                    ["Your output", r.stdout || r.stderr],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label}>
                    <p className="text-xs font-medium text-muted-foreground">{label}</p>
                    <pre className="mt-1 max-h-32 overflow-auto rounded bg-muted p-2 text-xs">
                      {value || "(empty)"}
                    </pre>
                  </div>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Solver({ problem, initialLanguage }: { problem: ProblemDetail; initialLanguage?: string | null }) {
  const first =
    problem.languages.find((l) => l.key === initialLanguage)?.key ?? problem.languages[0]?.key ?? "python";
  const [language, setLanguage] = useState(first);
  // Rendered only in the browser (after the problem loads), so the saved draft is readable here.
  const [code, setCode] = useState(() => readDraft(problem.slug, first) ?? problem.starters[first] ?? "");
  const [submissionId, setSubmissionId] = useState<string | null>(null);
  const [tab, setTab] = useState<"run" | "submit">("run");
  const run = useRunCode(problem.slug);
  const submitCode = useSubmitCode(problem.slug);
  const submission = useSubmission(submissionId);
  const history = useMySubmissions(problem.slug);

  function switchLanguage(next: string) {
    saveDraft(problem.slug, language, code);
    setLanguage(next);
    setCode(readDraft(problem.slug, next) ?? problem.starters[next] ?? "");
  }

  const limits = problem.languages.find((l) => l.key === language);
  const busy = run.isPending || submitCode.isPending || isPending(submission.data?.verdict);

  return (
    <div className="mx-auto grid max-w-7xl gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <Card className="h-fit p-5">
        <Button asChild variant="ghost" size="sm" className="mb-2 -ml-2">
          <Link href="/tests">
            <ArrowLeft /> All problems
          </Link>
        </Button>
        <h1 className="text-2xl font-semibold">{problem.title}</h1>
        <p className="mt-2 flex flex-wrap gap-1.5">
          <Badge variant={DIFFICULTY_VARIANT[problem.difficulty]}>{problem.difficulty}</Badge>
          {problem.topics.map((t) => (
            <Badge key={t} variant="muted">
              {t}
            </Badge>
          ))}
        </p>
        <div className="prose-sm mt-4 space-y-3 text-sm leading-relaxed [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_li]:ml-5 [&_li]:list-disc">
          <Markdown>{problem.statement}</Markdown>
        </div>
        <h2 className="mt-5 mb-2 text-sm font-semibold">Examples</h2>
        {problem.examples.map((ex, i) => (
          <div key={i} className="mb-3 grid gap-2 sm:grid-cols-2">
            <div>
              <p className="text-xs text-muted-foreground">Input</p>
              <pre className="mt-1 max-h-40 overflow-auto rounded-lg bg-muted p-2 text-xs">{ex.input}</pre>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Output</p>
              <pre className="mt-1 max-h-40 overflow-auto rounded-lg bg-muted p-2 text-xs">
                {ex.expected_output}
              </pre>
            </div>
          </div>
        ))}
        <p className="text-xs text-muted-foreground">
          Plus {problem.hidden_tests} hidden tests when you submit. Read from standard input; print to
          standard output.
        </p>
      </Card>

      <div className="space-y-4">
        <Card className="p-3">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <NativeSelect
              aria-label="Language"
              className="w-56"
              value={language}
              onChange={(e) => switchLanguage(e.target.value)}
            >
              {problem.languages.map((l) => (
                <option key={l.key} value={l.key}>
                  {l.name}
                </option>
              ))}
            </NativeSelect>
            {limits && (
              <span className="text-xs text-muted-foreground">
                {limits.time_limit_s}s · {limits.memory_limit_mb} MB
              </span>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="ml-auto"
              onClick={() => {
                setCode(problem.starters[language] ?? "");
                saveDraft(problem.slug, language, problem.starters[language] ?? "");
              }}
            >
              <RotateCcw /> Reset
            </Button>
          </div>
          <textarea
            aria-label="Code editor"
            value={code}
            onChange={(e) => {
              setCode(e.target.value);
              saveDraft(problem.slug, language, e.target.value);
            }}
            onKeyDown={(e) => handleEditorKey(e, setCode)}
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            className="min-h-[26rem] w-full resize-y rounded-lg border bg-muted/30 p-3 font-mono text-sm leading-relaxed focus-visible:outline-2 focus-visible:outline-ring"
          />
          <div className="mt-2 flex justify-end gap-2">
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                setTab("run");
                run.mutate({ language, code }, { onError: (e) => toast.error(errorMessage(e)) });
              }}
            >
              {run.isPending ? <Loader2 className="animate-spin" /> : <Play />} Run examples
            </Button>
            <Button
              variant="sunrise"
              disabled={busy}
              onClick={() => {
                setTab("submit");
                submitCode.mutate(
                  { language, code },
                  { onSuccess: (s) => setSubmissionId(s.id), onError: (e) => toast.error(errorMessage(e)) },
                );
              }}
            >
              {submitCode.isPending || isPending(submission.data?.verdict) ? (
                <Loader2 className="animate-spin" />
              ) : (
                <Send />
              )}
              Submit
            </Button>
          </div>
        </Card>

        <Card className="p-4">
          {tab === "run" && run.data ? (
            <Results
              verdict={run.data.verdict}
              passed={run.data.passed}
              total={run.data.total}
              results={run.data.results}
              compileOutput={run.data.compile_output}
            />
          ) : tab === "submit" && submission.data ? (
            <Results
              verdict={submission.data.verdict}
              passed={submission.data.passed}
              total={submission.data.total}
              results={submission.data.results}
              compileOutput={submission.data.compile_output}
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              Run your code against the examples, then submit to grade it against every test.
            </p>
          )}
        </Card>

        {history.data && history.data.length > 0 && (
          <Card className="p-4">
            <h2 className="mb-2 text-sm font-semibold">Your submissions</h2>
            <ul className="divide-y text-sm">
              {history.data.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    className={cn("flex w-full items-center gap-3 py-2 text-left hover:text-primary")}
                    onClick={() => {
                      setTab("submit");
                      setSubmissionId(s.id);
                    }}
                  >
                    <VerdictBadge verdict={s.verdict} />
                    <span>
                      {problem.languages.find((l) => l.key === s.language_key)?.name ?? s.language_key}
                    </span>
                    <span className="ml-auto text-xs text-muted-foreground">
                      {s.passed}/{s.total} · {formatDateTime(s.created_at)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </div>
  );
}

export function ProblemSolver({ slug, language }: { slug: string; language?: string | null }) {
  const problem = useProblem(slug);
  if (problem.isPending) return <Skeleton className="mx-auto h-[70dvh] max-w-7xl rounded-xl" />;
  if (problem.isError)
    return (
      <Card className="mx-auto max-w-xl">
        <ErrorState error={problem.error} onRetry={() => problem.refetch()} />
      </Card>
    );
  return <Solver key={problem.data.slug} problem={problem.data} initialLanguage={language} />;
}
