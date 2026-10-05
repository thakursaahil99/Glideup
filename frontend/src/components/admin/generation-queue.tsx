"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, RefreshCw, Sparkles, Upload, X } from "lucide-react";
import { useState } from "react";
import Markdown from "react-markdown";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge, Input, Label, NativeSelect, Skeleton } from "@/components/ui/primitives";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { DIFFICULTIES, type Difficulty, type GenerationItem } from "@/lib/api/types";

const KEY = ["admin", "generation"];
const onError = (e: unknown) => toast.error(errorMessage(e));

export function isGenerating(items: GenerationItem[] | undefined): boolean {
  return Boolean(items?.some((i) => i.status === "pending" || i.status === "generating"));
}

type DraftTest = { input: string; expected_output: string; hidden: boolean };

function Item({ item }: { item: GenerationItem }) {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: KEY });
  const review = useMutation({
    mutationFn: (body: { approve: boolean; publish: boolean; note?: string }) =>
      unwrap(api.POST("/api/v1/admin/question-generation/{item_id}/review", { params: { path: { item_id: item.id } }, body })),
    onSuccess: (r) => {
      toast.success(r.status === "approved" ? "Added to the question bank" : "Rejected");
      void refresh();
    },
    onError,
  });
  const retry = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/admin/question-generation/{item_id}/retry", { params: { path: { item_id: item.id } } })),
    onSuccess: () => refresh(),
    onError,
  });
  const draft = item.draft as { title?: string; statement?: string; tests?: DraftTest[]; reference?: Record<string, string> } | null;
  const failures = (item.validation as { failures?: unknown[] } | null)?.failures ?? [];

  return (
    <Card className="space-y-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={item.status === "ready" ? "success" : item.status === "failed" ? "destructive" : "muted"}>
          {item.status}
        </Badge>
        <span className="font-medium">{draft?.title ?? item.topic}</span>
        <span className="text-sm text-muted-foreground">
          {item.topic} · {item.difficulty}
          {item.generated_by && ` · ${item.generated_by}`}
        </span>
        <span className="ml-auto flex gap-2">
          {item.status === "ready" && (
            <>
              <Button size="sm" variant="outline" onClick={() => review.mutate({ approve: true, publish: false })} disabled={review.isPending}>
                <Check /> Approve as draft
              </Button>
              <Button size="sm" onClick={() => review.mutate({ approve: true, publish: true })} disabled={review.isPending}>
                <Upload /> Approve and publish
              </Button>
            </>
          )}
          {(item.status === "ready" || item.status === "failed") && (
            <Button size="sm" variant="ghost" onClick={() => review.mutate({ approve: false, publish: false })} disabled={review.isPending}>
              <X /> Reject
            </Button>
          )}
          {item.status === "failed" && (
            <Button size="sm" variant="ghost" onClick={() => retry.mutate()} disabled={retry.isPending}>
              <RefreshCw /> Retry
            </Button>
          )}
        </span>
      </div>
      {item.error && <p className="text-sm text-destructive">{item.error}</p>}
      {failures.length > 0 && (
        <pre className="max-h-32 overflow-auto rounded bg-destructive/10 p-2 text-xs">{JSON.stringify(failures, null, 2)}</pre>
      )}
      {draft?.statement && (
        <details>
          <summary className="cursor-pointer text-sm text-muted-foreground">
            Statement, {draft.tests?.length ?? 0} tests (outputs produced by running the reference) and solution
          </summary>
          <div className="mt-2 space-y-3 text-sm [&_code]:rounded [&_code]:bg-muted [&_code]:px-1">
            <Markdown>{draft.statement}</Markdown>
            <div className="grid gap-2 md:grid-cols-2">
              {draft.tests?.slice(0, 4).map((t, i) => (
                <pre key={i} className="max-h-28 overflow-auto rounded bg-muted p-2 text-xs">
                  {`${t.hidden ? "hidden" : "example"}\n${t.input.slice(0, 300)}\n→ ${t.expected_output.slice(0, 200)}`}
                </pre>
              ))}
            </div>
            {draft.reference?.python && (
              <pre className="max-h-64 overflow-auto rounded bg-muted p-2 text-xs">{draft.reference.python}</pre>
            )}
          </div>
        </details>
      )}
    </Card>
  );
}

export function GenerationQueueAdmin() {
  const client = useQueryClient();
  const [topic, setTopic] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [count, setCount] = useState(1);
  const list = useQuery({
    queryKey: KEY,
    queryFn: () => unwrap(api.GET("/api/v1/admin/question-generation")),
    refetchInterval: (query) => (isGenerating(query.state.data) ? 3000 : false),
  });
  const request = useMutation({
    mutationFn: () =>
      unwrap(api.POST("/api/v1/admin/question-generation", { body: { topic: topic.trim(), difficulty, count } })),
    onSuccess: () => {
      toast.success("Generating… each question is validated in the sandbox before review.");
      setTopic("");
      void client.invalidateQueries({ queryKey: KEY });
    },
    onError,
  });

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="AI generation queue"
        description="Generate problems by topic. The model writes the problem, inputs and a reference solution; the sandbox runs it to produce the expected outputs. You approve or reject."
      />
      <Card className="flex flex-wrap items-end gap-3 p-4">
        <div className="min-w-56 flex-1 space-y-1.5">
          <Label htmlFor="g-topic">Topic</Label>
          <Input id="g-topic" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. prefix sums, BFS on grids" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="g-diff">Difficulty</Label>
          <NativeSelect id="g-diff" className="w-32" value={difficulty} onChange={(e) => setDifficulty(e.target.value as Difficulty)}>
            {DIFFICULTIES.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="g-count">How many</Label>
          <Input id="g-count" type="number" min={1} max={5} className="w-20" value={count} onChange={(e) => setCount(Number(e.target.value))} />
        </div>
        <Button onClick={() => request.mutate()} disabled={request.isPending || topic.trim().length < 2}>
          {request.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />} Generate
        </Button>
      </Card>
      {list.isError ? (
        <Card>
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        </Card>
      ) : list.isPending ? (
        <Skeleton className="h-48 w-full" />
      ) : list.data.length === 0 ? (
        <Card>
          <EmptyState icon={<Sparkles className="size-5" aria-hidden />} title="Nothing generated yet" />
        </Card>
      ) : (
        <div className="space-y-3">
          {list.data.map((item) => (
            <Item key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
