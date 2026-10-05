"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FlaskConical, GitCompare, Loader2, RotateCcw, Save, Upload } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge, Input, Label, NativeSelect, Skeleton, Textarea } from "@/components/ui/primitives";
import { api, ApiError, errorMessage, unwrap } from "@/lib/api/client";
import type { PromptDetail, PromptTestResult, PromptVersion } from "@/lib/api/types";
import { diffLines } from "@/lib/diff";
import { cn, formatDateTime } from "@/lib/utils";

const onError = (e: unknown) => {
  const details = e instanceof ApiError && Array.isArray(e.details) ? ` ${e.details.join(" ")}` : "";
  toast.error(errorMessage(e) + details);
};

function Diff({ before, after }: { before: string; after: string }) {
  const lines = diffLines(before, after);
  if (!lines.some((l) => l.type !== "same")) return <p className="text-sm text-muted-foreground">No differences.</p>;
  return (
    <pre className="max-h-96 overflow-auto rounded-lg border bg-muted/40 p-3 text-xs leading-relaxed">
      {lines.map((line, i) => (
        <div
          key={i}
          className={cn(
            line.type === "added" && "bg-success/15 text-success",
            line.type === "removed" && "bg-destructive/10 text-destructive line-through",
          )}
        >
          {line.type === "added" ? "+ " : line.type === "removed" ? "- " : "  "}
          {line.text || " "}
        </div>
      ))}
    </pre>
  );
}

function Playground({ detail, system, user }: { detail: PromptDetail; system: string; user: string }) {
  const [variables, setVariables] = useState(() => JSON.stringify(detail.sample, null, 2));
  const [result, setResult] = useState<PromptTestResult | null>(null);
  const run = useMutation({
    mutationFn: async () => {
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(variables) as Record<string, unknown>;
      } catch {
        throw new Error("The example values aren't valid JSON.");
      }
      return unwrap(
        api.POST("/api/v1/admin/prompts/{name}/test", {
          params: { path: { name: detail.name } },
          body: { system, user, variables: parsed },
        }),
      );
    },
    onSuccess: setResult,
    onError,
  });
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="vars">Example values (JSON)</Label>
        <Textarea
          id="vars"
          className="min-h-40 font-mono text-xs"
          value={variables}
          onChange={(e) => setVariables(e.target.value)}
          spellCheck={false}
        />
      </div>
      <Button onClick={() => run.mutate()} disabled={run.isPending}>
        {run.isPending ? <Loader2 className="animate-spin" /> : <FlaskConical />} Run with the editor&apos;s text
      </Button>
      {result && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            {result.provider}:{result.model} · {(result.latency_ms / 1000).toFixed(1)} s · nothing was saved
          </p>
          <pre className="max-h-80 overflow-auto rounded-lg border bg-card p-3 text-xs whitespace-pre-wrap">
            {result.output}
          </pre>
          <details className="text-xs">
            <summary className="cursor-pointer text-muted-foreground">Rendered prompt</summary>
            {result.messages.map((m, i) => (
              <pre key={i} className="mt-2 overflow-auto rounded-lg bg-muted p-3 whitespace-pre-wrap">
                [{m.role}]{"\n"}
                {m.content}
              </pre>
            ))}
          </details>
        </div>
      )}
    </div>
  );
}

function Editor({ detail }: { detail: PromptDetail }) {
  const client = useQueryClient();
  const active = detail.versions.find((v) => v.active) ?? detail.versions[0];
  const [base, setBase] = useState<PromptVersion | undefined>(active);
  const [system, setSystem] = useState(active?.system ?? "");
  const [user, setUser] = useState(active?.user ?? "");
  const [notes, setNotes] = useState("");
  const [compareWith, setCompareWith] = useState<number | null>(null);
  const [tab, setTab] = useState<"edit" | "diff" | "test">("edit");
  const dirty = system !== base?.system || user !== base?.user;
  const refresh = (data: PromptDetail) => client.setQueryData(["admin", "prompt", detail.name], data);

  const save = useMutation({
    mutationFn: (activate: boolean) =>
      unwrap(
        api.POST("/api/v1/admin/prompts/{name}/versions", {
          params: { path: { name: detail.name } },
          body: { system, user, notes: notes || null, activate },
        }),
      ),
    onSuccess: (data, activate) => {
      refresh(data);
      setBase(data.versions[0]);
      setNotes("");
      toast.success(`Saved v${data.versions[0].version}${activate ? " and published it" : ""}`);
    },
    onError,
  });
  const activate = useMutation({
    mutationFn: (version: number) =>
      unwrap(
        api.POST("/api/v1/admin/prompts/{name}/activate", {
          params: { path: { name: detail.name } },
          body: { version },
        }),
      ),
    onSuccess: (data) => {
      refresh(data);
      toast.success(`v${data.active_version} is live`);
    },
    onError,
  });

  function load(version: PromptVersion) {
    setBase(version);
    setSystem(version.system);
    setUser(version.user);
  }

  const other = detail.versions.find((v) => v.version === compareWith);
  return (
    <div className="grid gap-4 lg:grid-cols-[14rem_1fr]">
      <nav aria-label="Versions" className="space-y-1">
        {detail.versions.map((v) => (
          <button
            key={v.version}
            type="button"
            onClick={() => load(v)}
            aria-current={base?.version === v.version}
            className={cn(
              "w-full rounded-lg border p-2 text-left text-sm transition-colors hover:bg-accent",
              base?.version === v.version && "border-primary bg-primary-soft",
            )}
          >
            <span className="flex items-center justify-between font-medium">
              v{v.version}
              {v.active && (
                <Badge variant="success">
                  <CheckCircle2 className="size-3" /> live
                </Badge>
              )}
            </span>
            <span className="block text-xs text-muted-foreground">
              {v.source === "file" ? "shipped" : (v.created_by_email ?? "admin")} · {formatDateTime(v.created_at)}
            </span>
            {v.notes && <span className="block truncate text-xs text-muted-foreground">{v.notes}</span>}
          </button>
        ))}
      </nav>

      <div className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div role="tablist" aria-label="Prompt tools" className="inline-flex rounded-lg border bg-card p-0.5">
            {(
              [
                ["edit", "Edit"],
                ["diff", "Compare"],
                ["test", "Test"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                role="tab"
                type="button"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={cn(
                  "rounded-md px-3 py-1 text-sm font-medium",
                  tab === id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          {base && !base.active && (
            <Button variant="outline" size="sm" onClick={() => activate.mutate(base.version)} disabled={activate.isPending}>
              <RotateCcw /> Make v{base.version} live
            </Button>
          )}
        </div>

        {tab === "edit" && (
          <>
            <p className="text-xs text-muted-foreground">
              Variables you can use: {detail.variables.map((v) => `{{ ${v} }}`).join(", ")}. Wrap untrusted text
              with <code>fence(text, &quot;tag&quot;)</code>.
            </p>
            <div className="space-y-1.5">
              <Label htmlFor="sys">System prompt</Label>
              <Textarea
                id="sys"
                className="min-h-72 font-mono text-xs"
                value={system}
                onChange={(e) => setSystem(e.target.value)}
                spellCheck={false}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="usr">User prompt</Label>
              <Textarea
                id="usr"
                className="min-h-32 font-mono text-xs"
                value={user}
                onChange={(e) => setUser(e.target.value)}
                spellCheck={false}
              />
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-56 flex-1 space-y-1.5">
                <Label htmlFor="notes">What changed</Label>
                <Input id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} />
              </div>
              <Button variant="outline" onClick={() => save.mutate(false)} disabled={!dirty || save.isPending}>
                <Save /> Save as new version
              </Button>
              <Button onClick={() => save.mutate(true)} disabled={!dirty || save.isPending}>
                <Upload /> Save and publish
              </Button>
            </div>
          </>
        )}

        {tab === "diff" && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <GitCompare className="size-4 text-muted-foreground" aria-hidden />
              <Label htmlFor="compare">Compare the editor with</Label>
              <NativeSelect
                id="compare"
                className="w-40"
                value={compareWith ?? ""}
                onChange={(e) => setCompareWith(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">Choose…</option>
                {detail.versions.map((v) => (
                  <option key={v.version} value={v.version}>
                    v{v.version}
                    {v.active ? " (live)" : ""}
                  </option>
                ))}
              </NativeSelect>
            </div>
            {other ? (
              <>
                <h3 className="text-sm font-medium">System</h3>
                <Diff before={other.system} after={system} />
                <h3 className="text-sm font-medium">User</h3>
                <Diff before={other.user} after={user} />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Pick a version to see what the editor changes.</p>
            )}
          </div>
        )}

        {tab === "test" && <Playground detail={detail} system={system} user={user} />}
      </div>
    </div>
  );
}

function PromptPanel({ name }: { name: string }) {
  const detail = useQuery({
    queryKey: ["admin", "prompt", name],
    queryFn: () => unwrap(api.GET("/api/v1/admin/prompts/{name}", { params: { path: { name } } })),
  });
  if (detail.isError) return <ErrorState error={detail.error} onRetry={() => detail.refetch()} />;
  if (detail.isPending) return <Skeleton className="h-96 w-full" />;
  return <Editor key={name} detail={detail.data} />;
}

export function PromptsAdmin() {
  const list = useQuery({
    queryKey: ["admin", "prompts"],
    queryFn: () => unwrap(api.GET("/api/v1/admin/prompts")),
  });
  const [selected, setSelected] = useState<string | null>(null);
  const current = selected ?? list.data?.[0]?.name ?? null;
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Prompt templates"
        description="Every prompt GlideUp sends to a model. Edits create versions; publishing and rollback take effect within 30 seconds and are audited."
      />
      {list.isError ? (
        <Card>
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        </Card>
      ) : list.isPending ? (
        <Skeleton className="h-96 w-full" />
      ) : list.data.length === 0 ? (
        <Card>
          <EmptyState title="No prompts found" />
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
          <Card className="h-fit p-2">
            <ul aria-label="Prompt templates">
              {list.data.map((p) => (
                <li key={p.name}>
                  <button
                    type="button"
                    onClick={() => setSelected(p.name)}
                    aria-current={current === p.name}
                    className={cn(
                      "w-full rounded-md p-2 text-left hover:bg-accent",
                      current === p.name && "bg-primary-soft",
                    )}
                  >
                    <span className="block font-mono text-sm">{p.name}</span>
                    <span className="block text-xs text-muted-foreground">
                      v{p.active_version} live · {p.versions} version{p.versions === 1 ? "" : "s"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          <Card className="p-4">
            {current && (
              <>
                <p className="mb-4 text-sm text-muted-foreground">
                  {list.data.find((p) => p.name === current)?.description}
                </p>
                <PromptPanel name={current} />
              </>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
