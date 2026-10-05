"use client";

import {
  ArrowRight,
  Clock,
  Flag,
  Lightbulb,
  Loader2,
  Play,
  SendHorizontal,
  SkipForward,
  WifiOff,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { Badge, Skeleton, Textarea } from "@/components/ui/primitives";
import { useInterview } from "@/lib/api/interviews";
import type { InterviewDetail, InterviewMessage, InterviewState } from "@/lib/api/types";
import { useInterviewRoom } from "@/lib/interview-room";
import { cn } from "@/lib/utils";

export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function useSecondsLeft(endsAt: string | null | undefined): number | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!endsAt) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [endsAt]);
  return endsAt ? (new Date(endsAt).getTime() - now) / 1000 : null;
}

function Bubble({ role, kind, children, live }: { role: string; kind: string; children: string; live?: boolean }) {
  const mine = role === "candidate";
  return (
    <div className={cn("flex", mine ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap",
          mine ? "bg-primary text-primary-foreground" : "border bg-card",
          kind === "question" && "border-primary/40 bg-primary-soft",
          kind === "hint" && "border-sunrise/50 bg-sunrise-soft",
          kind === "skip" && "opacity-70",
        )}
      >
        {kind === "hint" && (
          <span className="mb-1 flex items-center gap-1 text-xs font-medium text-sunrise-foreground dark:text-sunrise">
            <Lightbulb className="size-3.5" aria-hidden /> Hint
          </span>
        )}
        {children}
        {live && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-current align-middle" />}
      </div>
    </div>
  );
}

function Transcript({ messages, streaming }: { messages: InterviewMessage[]; streaming: { kind: string; text: string } | null }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [messages.length, streaming?.text]);
  return (
    <div className="space-y-3" aria-live="polite" aria-relevant="additions">
      {messages.map((m) => (
        <div key={m.id}>
          <Bubble role={m.role} kind={m.kind}>
            {m.content}
          </Bubble>
          {m.attachment && (
            <pre className="mt-1 ml-auto max-w-[85%] overflow-x-auto rounded-lg bg-muted p-3 text-xs">
              {m.attachment}
            </pre>
          )}
        </div>
      ))}
      {streaming && (
        <Bubble role="interviewer" kind={streaming.kind} live>
          {streaming.text}
        </Bubble>
      )}
      <div ref={end} />
    </div>
  );
}

function ReadyScreen({ detail, onStart, disabled }: { detail: InterviewState; onStart: () => void; disabled: boolean }) {
  return (
    <Card className="mx-auto max-w-xl p-6 text-center">
      <h2 className="text-xl font-semibold">Ready when you are</h2>
      <p className="mt-2 text-muted-foreground">
        {detail.total_questions} question{detail.total_questions === 1 ? "" : "s"} · {detail.duration_minutes}{" "}
        minutes · {detail.difficulty}
      </p>
      <ul className="mt-4 space-y-1 text-left text-sm text-muted-foreground">
        <li>• The clock starts when you press Start.</li>
        <li>• Think out loud: explain your reasoning, not just the answer.</li>
        <li>• Ask for a hint if you get stuck; it&apos;s noted in your report.</li>
        <li>• You can leave and come back; the interview continues until time runs out.</li>
      </ul>
      <Button className="mt-6" variant="sunrise" size="lg" onClick={onStart} disabled={disabled}>
        <Play /> Start interview
      </Button>
    </Card>
  );
}

function Room({ detail }: { detail: InterviewDetail }) {
  const room = useInterviewRoom(detail.interview.id, detail);
  const { state } = room;
  const interview = state.interview ?? detail.interview;
  const secondsLeft = useSecondsLeft(interview.status === "in_progress" ? interview.ends_at : null);
  const [draft, setDraft] = useState("");
  const [panel, setPanel] = useState("");
  const [confirmEnd, setConfirmEnd] = useState(false);
  const kind = interview.current_kind;
  const showPanel = interview.status === "in_progress" && (kind === "coding" || kind === "design");
  const canAct = state.connection === "open" && !state.busy && interview.status === "in_progress";

  function submit() {
    if (!draft.trim() && !panel.trim()) return;
    if (room.answer(draft, showPanel ? panel : undefined)) setDraft("");
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <header className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold">
            {state.typeName || detail.type_name} interview
            {interview.job_title && (
              <span className="font-normal text-muted-foreground">
                {" "}
                · {interview.job_title} at {interview.company_name}
              </span>
            )}
          </h1>
          {interview.status === "in_progress" && (
            <p className="text-sm text-muted-foreground">
              Question {Math.min(interview.current_index + 1, interview.total_questions)} of{" "}
              {interview.total_questions}
              {interview.hints_used > 0 && ` · ${interview.hints_used} hint${interview.hints_used === 1 ? "" : "s"} used`}
            </p>
          )}
        </div>
        {secondsLeft !== null && (
          <Badge
            variant={secondsLeft < 300 ? "sunrise" : "outline"}
            className="px-3 py-1 text-sm tabular-nums"
            aria-label={`${Math.ceil(secondsLeft / 60)} minutes left`}
          >
            <Clock className="size-4" aria-hidden /> {formatClock(secondsLeft)}
          </Badge>
        )}
        {state.connection !== "open" && interview.status !== "completed" && (
          <Badge variant="muted" role="status">
            {state.connection === "closed" ? (
              <WifiOff className="size-3.5" aria-hidden />
            ) : (
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
            )}
            {state.connection === "connecting"
              ? "Connecting"
              : state.connection === "reconnecting"
                ? "Reconnecting"
                : "Offline"}
          </Badge>
        )}
      </header>

      {state.error && (
        <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
          {state.error}
        </p>
      )}

      {interview.status === "ready" ? (
        <ReadyScreen detail={interview} onStart={room.start} disabled={state.connection !== "open" || state.busy} />
      ) : (
        <div className={cn("grid gap-4", showPanel && "lg:grid-cols-[1fr_26rem]")}>
          <Card className="flex min-h-[60dvh] flex-col">
            <div className="flex-1 overflow-y-auto p-4 sm:p-5">
              <Transcript messages={state.messages} streaming={state.streaming} />
            </div>
            {interview.status === "completed" ? (
              <div className="flex flex-wrap items-center justify-between gap-3 border-t p-4">
                <p className="text-sm text-muted-foreground">This interview has ended.</p>
                <Button asChild variant="sunrise">
                  <Link href={`/interviews/${interview.id}/report`}>
                    See your report <ArrowRight />
                  </Link>
                </Button>
              </div>
            ) : (
              <form
                className="border-t p-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  submit();
                }}
              >
                <Textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                      e.preventDefault();
                      submit();
                    }
                  }}
                  placeholder="Type your answer… (Ctrl+Enter to send)"
                  aria-label="Your answer"
                  rows={3}
                  maxLength={6000}
                />
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <Button type="button" variant="ghost" size="sm" onClick={room.hint} disabled={!canAct}>
                    <Lightbulb /> Hint
                  </Button>
                  <Button type="button" variant="ghost" size="sm" onClick={room.skip} disabled={!canAct}>
                    <SkipForward /> Skip question
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setConfirmEnd(true)}
                    disabled={state.connection !== "open" || state.busy}
                  >
                    <Flag /> End
                  </Button>
                  <Button type="submit" className="ml-auto" disabled={!canAct || (!draft.trim() && !panel.trim())}>
                    {state.busy ? <Loader2 className="animate-spin" /> : <SendHorizontal />} Send
                  </Button>
                </div>
              </form>
            )}
          </Card>

          {showPanel && (
            <Card className="flex flex-col p-3">
              <label htmlFor="panel" className="mb-2 text-sm font-medium">
                {kind === "coding" ? "Code" : "Design notes"}
              </label>
              <p className="mb-2 text-xs text-muted-foreground">
                {kind === "coding"
                  ? "Write your solution here; it's sent with your next answer."
                  : "List components, data flow and storage choices; sent with your next answer."}
              </p>
              <Textarea
                id="panel"
                value={panel}
                onChange={(e) => setPanel(e.target.value)}
                spellCheck={false}
                className="min-h-80 flex-1 font-mono text-sm"
                maxLength={20000}
              />
            </Card>
          )}
        </div>
      )}

      <Dialog open={confirmEnd} onOpenChange={setConfirmEnd}>
        <DialogContent>
          <DialogTitle>End the interview now?</DialogTitle>
          <DialogDescription>
            Unanswered questions score 0 in your report. You can&apos;t resume an ended interview.
          </DialogDescription>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmEnd(false)}>
              Keep going
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setConfirmEnd(false);
                room.end();
              }}
            >
              End interview
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function InterviewRoom({ interviewId }: { interviewId: string }) {
  const { data, isPending, isError, error, refetch } = useInterview(interviewId);
  if (isPending) return <Skeleton className="mx-auto h-[60dvh] max-w-6xl rounded-xl" />;
  if (isError)
    return (
      <Card className="mx-auto max-w-xl">
        <ErrorState error={error} onRetry={() => refetch()} />
      </Card>
    );
  if (data.interview.status === "preparing")
    return (
      <Card className="mx-auto max-w-xl p-8 text-center" role="status">
        <Loader2 className="mx-auto size-8 animate-spin text-primary" aria-hidden />
        <p className="mt-4 font-medium">Writing questions for {data.interview.job_title}…</p>
        <p className="mt-1 text-sm text-muted-foreground">
          We read the job description and your resume. This usually takes under a minute.
        </p>
      </Card>
    );
  if (data.interview.status === "failed")
    return (
      <Card className="mx-auto max-w-xl p-8 text-center">
        <p className="font-medium">We couldn&apos;t prepare this interview.</p>
        <p className="mt-1 text-sm text-muted-foreground">{data.error}</p>
        <Button asChild className="mt-4">
          <Link href="/interviews">Back to interviews</Link>
        </Button>
      </Card>
    );
  return <Room key={data.interview.id} detail={data} />;
}
