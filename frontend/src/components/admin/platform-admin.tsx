"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Plus, RefreshCw, RotateCcw, Save } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge, Input, Label, NativeSelect, Skeleton, Textarea } from "@/components/ui/primitives";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Announcement, FeatureFlag, HealthCheck, LLMSettings } from "@/lib/api/types";
import { cn, formatDateTime } from "@/lib/utils";

const onError = (e: unknown) => toast.error(errorMessage(e));

// ------------------------------------------------------------------ feature flags

function FlagRow({ flag }: { flag: FeatureFlag }) {
  const client = useQueryClient();
  const [percent, setPercent] = useState(flag.rollout_percent);
  const [testers, setTesters] = useState(flag.allow_user_ids.join(", "));
  const save = useMutation({
    mutationFn: (body: { enabled?: boolean; rollout_percent?: number; allow_user_ids?: string[] }) =>
      unwrap(api.PATCH("/api/v1/admin/flags/{key}", { params: { path: { key: flag.key } }, body })),
    onSuccess: () => {
      toast.success("Saved. Takes effect within 30 seconds.");
      void client.invalidateQueries({ queryKey: ["admin", "flags"] });
    },
    onError,
  });
  return (
    <TableRow>
      <TableCell>
        <p className="font-mono text-sm">{flag.key}</p>
        <p className="text-xs text-muted-foreground">{flag.description}</p>
      </TableCell>
      <TableCell>
        <input
          type="checkbox"
          className="size-4 accent-primary"
          aria-label={`${flag.key} enabled`}
          checked={flag.enabled}
          onChange={(e) => save.mutate({ enabled: e.target.checked })}
        />
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-1">
          <Input
            aria-label={`${flag.key} rollout percent`}
            type="number"
            min={0}
            max={100}
            className="h-8 w-20"
            value={percent}
            onChange={(e) => setPercent(Number(e.target.value))}
            onBlur={() => percent !== flag.rollout_percent && save.mutate({ rollout_percent: percent })}
          />
          <span className="text-xs text-muted-foreground">%</span>
        </div>
      </TableCell>
      <TableCell>
        <Input
          aria-label={`${flag.key} tester user ids`}
          placeholder="user ids, comma-separated"
          className="h-8"
          value={testers}
          onChange={(e) => setTesters(e.target.value)}
          onBlur={() => {
            const ids = testers.split(",").map((t) => t.trim()).filter(Boolean);
            if (ids.join(",") !== flag.allow_user_ids.join(",")) save.mutate({ allow_user_ids: ids });
          }}
        />
      </TableCell>
    </TableRow>
  );
}

export function FlagsAdmin() {
  const flags = useQuery({ queryKey: ["admin", "flags"], queryFn: () => unwrap(api.GET("/api/v1/admin/flags")) });
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Feature flags"
        description="Turn features on or off without a deploy: for everyone, a share of users, or named testers."
      />
      <Card>
        {flags.isError ? (
          <ErrorState error={flags.error} onRetry={() => flags.refetch()} />
        ) : flags.isPending ? (
          <Skeleton className="m-4 h-48" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Flag</TableHead>
                <TableHead>On</TableHead>
                <TableHead>Rollout</TableHead>
                <TableHead>Always on for</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {flags.data.map((f) => (
                <FlagRow key={f.key} flag={f} />
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ AI / LLM settings

function RoutesEditor({ data }: { data: LLMSettings }) {
  const client = useQueryClient();
  const overrides = (data.settings["llm.routes"] ?? {}) as Record<string, string[]>;
  const [routes, setRoutes] = useState<Record<string, string>>(() =>
    Object.fromEntries(data.tasks.map((t) => [t, (overrides[t] ?? []).join(", ")])),
  );
  const [cacheOn, setCacheOn] = useState(Boolean(data.settings["llm.cache_enabled"]));
  const [ttl, setTtl] = useState(Number(data.settings["llm.cache_ttl_hours"] ?? 24));
  const [budget, setBudget] = useState(Number(data.settings["llm.user_daily_token_budget"] ?? 0));
  const save = useMutation({
    mutationFn: () =>
      unwrap(
        api.PUT("/api/v1/admin/llm/settings", {
          body: {
            values: {
              "llm.routes": Object.fromEntries(
                Object.entries(routes).map(([t, v]) => [t, v.split(",").map((s) => s.trim()).filter(Boolean)]),
              ),
              "llm.cache_enabled": cacheOn,
              "llm.cache_ttl_hours": ttl,
              "llm.user_daily_token_budget": budget,
            },
          },
        }),
      ),
    onSuccess: (next) => {
      client.setQueryData(["admin", "llm"], next);
      toast.success("Saved. Every worker picks it up within 30 seconds.");
    },
    onError,
  });
  return (
    <div className="space-y-5 p-4">
      <p className="text-sm text-muted-foreground">
        Configured providers: {data.providers.map((p) => <Badge key={p} variant="muted" className="mr-1">{p}</Badge>)}
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Task</TableHead>
            <TableHead>Override (provider:model, in fallback order)</TableHead>
            <TableHead>In effect</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.tasks.map((task) => (
            <TableRow key={task}>
              <TableCell className="font-mono text-xs">{task}</TableCell>
              <TableCell>
                <Input
                  aria-label={`Routes for ${task}`}
                  className="h-8 font-mono text-xs"
                  placeholder="empty = default"
                  value={routes[task] ?? ""}
                  onChange={(e) => setRoutes({ ...routes, [task]: e.target.value })}
                />
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">{data.effective_routes[task]?.join(" → ")}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-primary" checked={cacheOn} onChange={(e) => setCacheOn(e.target.checked)} />
          Response cache
        </label>
        <div className="space-y-1">
          <Label htmlFor="ttl">Cache TTL (hours)</Label>
          <Input id="ttl" type="number" min={1} max={720} className="w-28" value={ttl} onChange={(e) => setTtl(Number(e.target.value))} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="budget">Daily tokens per user (0 = unlimited)</Label>
          <Input id="budget" type="number" min={0} className="w-40" value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
        </div>
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          <Save /> Save settings
        </Button>
      </div>
    </div>
  );
}

function UsageTable() {
  const [days, setDays] = useState(7);
  const usage = useQuery({
    queryKey: ["admin", "llm-usage", days],
    queryFn: () => unwrap(api.GET("/api/v1/admin/llm/usage", { params: { query: { days } } })),
  });
  return (
    <Card>
      <div className="flex items-center gap-3 border-b p-4">
        <h2 className="font-semibold">Usage, cost and latency</h2>
        <NativeSelect aria-label="Period" className="ml-auto w-32" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={1}>24 hours</option>
          <option value={7}>7 days</option>
          <option value={30}>30 days</option>
        </NativeSelect>
      </div>
      {usage.isPending ? (
        <Skeleton className="m-4 h-32" />
      ) : !usage.data?.length ? (
        <EmptyState title="No LLM calls in this period" />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Provider / model</TableHead>
              <TableHead>Task</TableHead>
              <TableHead className="text-right">Calls</TableHead>
              <TableHead className="text-right">Errors</TableHead>
              <TableHead className="text-right">Cached</TableHead>
              <TableHead className="text-right">Tokens</TableHead>
              <TableHead className="text-right">Cost</TableHead>
              <TableHead className="text-right">Avg latency</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {usage.data.map((row, i) => (
              <TableRow key={i}>
                <TableCell className="text-xs">
                  {String(row.provider)}:{String(row.model)}
                </TableCell>
                <TableCell className="font-mono text-xs">{String(row.task)}</TableCell>
                <TableCell className="text-right tabular-nums">{String(row.calls)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {String(row.errors)} ({Math.round(Number(row.error_rate) * 100)}%)
                </TableCell>
                <TableCell className="text-right tabular-nums">{String(row.cached)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {(Number(row.prompt_tokens) + Number(row.completion_tokens)).toLocaleString()}
                </TableCell>
                <TableCell className="text-right tabular-nums">${Number(row.cost_usd).toFixed(4)}</TableCell>
                <TableCell className="text-right tabular-nums">{String(row.avg_latency_ms)} ms</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}

export function LLMAdmin() {
  const settings = useQuery({ queryKey: ["admin", "llm"], queryFn: () => unwrap(api.GET("/api/v1/admin/llm/settings")) });
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="AI / LLM settings"
        description="Which model serves each task and in what fallback order, the response cache, and per-user token budgets."
      />
      <Card>
        {settings.isError ? (
          <ErrorState error={settings.error} onRetry={() => settings.refetch()} />
        ) : settings.isPending ? (
          <Skeleton className="m-4 h-64" />
        ) : (
          <RoutesEditor key={settings.dataUpdatedAt} data={settings.data} />
        )}
      </Card>
      <UsageTable />
    </div>
  );
}

// ------------------------------------------------------------------ system health

const STATUS_VARIANT = { ok: "success", degraded: "sunrise", down: "destructive", off: "muted" } as const;

function CheckCard({ check }: { check: HealthCheck }) {
  return (
    <Card className="p-4">
      <p className="flex items-center justify-between gap-2">
        <span className="font-medium">{check.name}</span>
        <Badge variant={STATUS_VARIANT[check.status]}>{check.status}</Badge>
      </p>
      <p className="mt-1 text-sm text-muted-foreground">
        {check.detail || "—"}
        {check.latency_ms != null && ` · ${check.latency_ms} ms`}
      </p>
      {Object.entries(check.extra).map(([k, v]) => (
        <p key={k} className="text-xs text-muted-foreground">
          {k.replaceAll("_", " ")}: {String(v)}
        </p>
      ))}
    </Card>
  );
}

export function HealthAdmin({ canRetry }: { canRetry: boolean }) {
  const client = useQueryClient();
  const health = useQuery({
    queryKey: ["admin", "health"],
    queryFn: () => unwrap(api.GET("/api/v1/admin/system/health")),
    refetchInterval: 15_000,
  });
  const retry = useMutation({
    mutationFn: ({ kind, id }: { kind: string; id: string }) =>
      unwrap(api.POST("/api/v1/admin/system/jobs/{kind}/{item_id}/retry", { params: { path: { kind, item_id: id } } })),
    onSuccess: () => {
      toast.success("Queued for retry");
      void client.invalidateQueries({ queryKey: ["admin", "health"] });
    },
    onError,
  });
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="System health"
        description="Every dependency, checked live (refreshes every 15 seconds), and background jobs that failed."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => health.refetch()} disabled={health.isFetching}>
              <RefreshCw className={cn(health.isFetching && "animate-spin")} /> Refresh
            </Button>
            {health.data?.grafana_url && (
              <Button asChild variant="outline" size="sm">
                <a href={health.data.grafana_url} target="_blank" rel="noreferrer noopener">
                  Grafana <ExternalLink />
                </a>
              </Button>
            )}
          </>
        }
      />
      {health.isError ? (
        <Card>
          <ErrorState error={health.error} onRetry={() => health.refetch()} />
        </Card>
      ) : health.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {health.data.checks.map((c) => (
              <CheckCard key={c.name} check={c} />
            ))}
          </div>
          <Card>
            <h2 className="border-b p-4 font-semibold">Failed background jobs (last 7 days)</h2>
            {health.data.failed_jobs.length === 0 ? (
              <EmptyState title="No failed jobs" />
            ) : (
              <ul className="divide-y">
                {health.data.failed_jobs.map((job) => (
                  <li key={`${job.kind}:${job.id}`} className="flex flex-wrap items-center gap-3 p-4 text-sm">
                    <Badge variant="muted">{job.kind.replaceAll("_", " ")}</Badge>
                    <span className="font-medium">{job.label}</span>
                    <span className="min-w-0 flex-1 truncate text-muted-foreground">{job.error}</span>
                    <span className="text-xs text-muted-foreground">{formatDateTime(job.at)}</span>
                    {canRetry && (
                      <Button size="sm" variant="outline" onClick={() => retry.mutate({ kind: job.kind, id: job.id })} disabled={retry.isPending}>
                        <RotateCcw /> Retry
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ announcements

export function AnnouncementsAdmin() {
  const client = useQueryClient();
  const list = useQuery({ queryKey: ["admin", "announcements"], queryFn: () => unwrap(api.GET("/api/v1/admin/announcements")) });
  const [form, setForm] = useState({ title: "", body: "", level: "info" as "info" | "warning", audience: "all" as "all" | "admins", ends_at: "" });
  const create = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/admin/announcements", {
          body: { ...form, ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null, active: true },
        }),
      ),
    onSuccess: () => {
      toast.success("Published");
      setForm({ ...form, title: "", body: "" });
      void client.invalidateQueries({ queryKey: ["admin", "announcements"] });
    },
    onError,
  });
  const toggle = useMutation({
    mutationFn: (a: Announcement) =>
      unwrap(
        api.PATCH("/api/v1/admin/announcements/{announcement_id}", {
          params: { path: { announcement_id: a.id } },
          body: { title: a.title, body: a.body, level: a.level as "info" | "warning", audience: a.audience as "all" | "admins",
                  starts_at: a.starts_at, ends_at: a.ends_at, active: !a.active },
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: ["admin", "announcements"] }),
    onError,
  });
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader title="Announcements" description="Banners shown at the top of the app, to everyone or to admins only." />
      <Card className="space-y-3 p-4">
        <div className="space-y-1.5">
          <Label htmlFor="an-title">Title</Label>
          <Input id="an-title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="an-body">Message (optional)</Label>
          <Textarea id="an-body" value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <NativeSelect aria-label="Level" className="w-32" value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value as "info" | "warning" })}>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
          </NativeSelect>
          <NativeSelect aria-label="Audience" className="w-36" value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value as "all" | "admins" })}>
            <option value="all">Everyone</option>
            <option value="admins">Admins only</option>
          </NativeSelect>
          <div className="space-y-1">
            <Label htmlFor="an-ends">Ends (optional)</Label>
            <Input id="an-ends" type="datetime-local" className="w-56" value={form.ends_at} onChange={(e) => setForm({ ...form, ends_at: e.target.value })} />
          </div>
          <Button onClick={() => create.mutate()} disabled={!form.title.trim() || create.isPending}>
            <Plus /> Publish
          </Button>
        </div>
      </Card>
      <Card>
        {list.isPending ? (
          <Skeleton className="m-4 h-32" />
        ) : !list.data?.length ? (
          <EmptyState title="No announcements yet" />
        ) : (
          <ul className="divide-y">
            {list.data.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-3 p-4 text-sm">
                <Badge variant={a.level === "warning" ? "sunrise" : "default"}>{a.level}</Badge>
                <span className="flex-1 font-medium">{a.title}</span>
                <span className="text-xs text-muted-foreground">
                  {a.audience} · {a.ends_at ? `until ${formatDateTime(a.ends_at)}` : "no end"}
                </span>
                <Button size="sm" variant="outline" onClick={() => toggle.mutate(a)}>
                  {a.active ? "Turn off" : "Turn on"}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
