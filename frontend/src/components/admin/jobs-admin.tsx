"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  EyeOff,
  History,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  Star,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Pagination } from "@/components/admin/pagination";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge, Input, Label, NativeSelect, Skeleton } from "@/components/ui/primitives";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, ApiError, errorMessage, unwrap } from "@/lib/api/client";
import type { Company, CompanyImportResult, IngestionRun, JobSource } from "@/lib/api/types";
import { useDebouncedValue } from "@/lib/hooks";
import { cn, formatDateTime } from "@/lib/utils";

type Tab = "sources" | "companies" | "jobs";
const onError = (e: unknown) => toast.error(errorMessage(e));

function useInvalidate() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ["admin", "jobs-admin"] });
}

function RunBadge({ run }: { run: IngestionRun | null | undefined }) {
  if (!run) return <Badge variant="muted">Never run</Badge>;
  const variant = {
    success: "success",
    partial: "sunrise",
    failed: "destructive",
    running: "default",
  } as const;
  return <Badge variant={variant[run.status]}>{run.status}</Badge>;
}

function schedule(minutes: number) {
  return minutes % 60 === 0 ? `every ${minutes / 60}h` : `every ${minutes} min`;
}

// ------------------------------------------------------------------ sources

const NEWLINE = String.fromCharCode(10);
type CountryOption = { code: string; name: string };
type AdzunaConfig = { countries: string[]; queries: string[]; pages_per_query: number; max_days_old: number };

/** Adzuna: pick countries with checkboxes instead of editing JSON. */
function AdzunaConfigEditor({
  options,
  value,
  onChange,
}: {
  options: CountryOption[];
  value: AdzunaConfig;
  onChange: (next: AdzunaConfig) => void;
}) {
  const toggle = (code: string) =>
    onChange({
      ...value,
      countries: value.countries.includes(code)
        ? value.countries.filter((c) => c !== code)
        : [...value.countries, code],
    });
  return (
    <div className="space-y-4">
      <fieldset>
        <legend className="mb-2 flex w-full items-center justify-between text-sm font-medium">
          <span>
            Countries to read{" "}
            <span className="text-muted-foreground">({value.countries.length} selected)</span>
          </span>
          <span className="flex gap-2 text-xs">
            <button
              type="button"
              className="text-primary hover:underline"
              onClick={() => onChange({ ...value, countries: options.map((o) => o.code) })}
            >
              All
            </button>
            <button
              type="button"
              className="text-primary hover:underline"
              onClick={() => onChange({ ...value, countries: [] })}
            >
              None
            </button>
          </span>
        </legend>
        <div className="grid max-h-48 grid-cols-2 gap-1 overflow-y-auto rounded-lg border p-2 sm:grid-cols-3">
          {options.map((o) => (
            <label
              key={o.code}
              className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-accent"
            >
              <input
                type="checkbox"
                checked={value.countries.includes(o.code)}
                onChange={() => toggle(o.code)}
                className="size-4 accent-[var(--primary)]"
              />
              {o.name}
            </label>
          ))}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          Each country × search term is one request batch: more countries means longer runs.
        </p>
      </fieldset>
      <div className="space-y-1.5">
        <Label htmlFor="queries">Search terms (one per line)</Label>
        <textarea
          id="queries"
          value={value.queries.join(NEWLINE)}
          onChange={(e) => onChange({ ...value, queries: e.target.value.split(NEWLINE) })}
          className="min-h-24 w-full rounded-md border border-input bg-card p-2 text-sm"
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="pages">Pages per term (50 jobs each)</Label>
          <Input
            id="pages"
            type="number"
            min={1}
            max={5}
            value={value.pages_per_query}
            onChange={(e) => onChange({ ...value, pages_per_query: Number(e.target.value) })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="days-old">Max job age (days)</Label>
          <Input
            id="days-old"
            type="number"
            min={1}
            max={90}
            value={value.max_days_old}
            onChange={(e) => onChange({ ...value, max_days_old: Number(e.target.value) })}
          />
        </div>
      </div>
    </div>
  );
}

function SourceSettingsDialog({ source, onClose }: { source: JobSource; onClose: () => void }) {
  const [hours, setHours] = useState(String(source.schedule_minutes / 60));
  const [rate, setRate] = useState(String(source.rate_limit_per_minute));
  const options = source.config_options as {
    supported_countries?: CountryOption[];
    defaults?: AdzunaConfig;
  } | null;
  const [adzuna, setAdzuna] = useState<AdzunaConfig | null>(
    options?.supported_countries ? ({ ...options.defaults, ...source.config } as AdzunaConfig) : null,
  );
  const invalidate = useInvalidate();
  const save = useMutation({
    mutationFn: () =>
      unwrap(
        api.PATCH("/api/v1/admin/job-sources/{key}", {
          params: { path: { key: source.key } },
          body: {
            schedule_minutes: Math.round(Number(hours) * 60),
            rate_limit_per_minute: Number(rate),
            // Sources without settings (ATS boards) never send a config.
            ...(adzuna ? { config: { ...adzuna, queries: adzuna.queries.filter((q) => q.trim()) } } : {}),
          },
        }),
      ),
    onSuccess: () => {
      toast.success(`${source.name} updated`);
      invalidate();
      onClose();
    },
    onError,
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{source.name} settings</DialogTitle>
          <DialogDescription>
            Changes apply from the next run and are recorded in the audit log.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="hours">Run every (hours)</Label>
            <Input
              id="hours"
              type="number"
              min={0.25}
              step={0.25}
              value={hours}
              onChange={(e) => setHours(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rate">Requests per minute</Label>
            <Input
              id="rate"
              type="number"
              min={1}
              max={600}
              value={rate}
              onChange={(e) => setRate(e.target.value)}
            />
          </div>
        </div>
        {adzuna && options?.supported_countries && (
          <AdzunaConfigEditor options={options.supported_countries} value={adzuna} onChange={setAdzuna} />
        )}
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button
            onClick={() => save.mutate()}
            disabled={save.isPending || (adzuna !== null && adzuna.countries.length === 0)}
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RunsDialog({ source, onClose }: { source: JobSource; onClose: () => void }) {
  const runs = useQuery({
    queryKey: ["admin", "jobs-admin", "runs", source.key],
    queryFn: () =>
      unwrap(api.GET("/api/v1/admin/job-sources/{key}/runs", { params: { path: { key: source.key } } })),
  });
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{source.name}: recent runs</DialogTitle>
        </DialogHeader>
        {runs.isPending ? (
          <Skeleton className="h-48" />
        ) : runs.isError ? (
          <ErrorState error={runs.error} onRetry={() => runs.refetch()} />
        ) : runs.data.length === 0 ? (
          <EmptyState title="No runs yet" />
        ) : (
          <div className="max-h-[60vh] overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Started</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Fetched</TableHead>
                  <TableHead className="text-right">New</TableHead>
                  <TableHead className="text-right">Updated</TableHead>
                  <TableHead className="text-right">Retired</TableHead>
                  <TableHead className="text-right">Dupes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.data.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell className="whitespace-nowrap">
                      {formatDateTime(run.started_at)}
                      <span className="block text-xs text-muted-foreground">{run.trigger}</span>
                    </TableCell>
                    <TableCell>
                      <RunBadge run={run} />
                      {run.errors.length > 0 && (
                        <details className="mt-1 text-xs text-muted-foreground">
                          <summary className="cursor-pointer">{run.errors.length} error(s)</summary>
                          <ul className="mt-1 space-y-0.5">
                            {run.errors.map((e) => (
                              <li key={e} className="font-mono break-all">
                                {e}
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </TableCell>
                    {[run.fetched, run.created, run.updated, run.deactivated, run.duplicates].map((n, i) => (
                      <TableCell key={i} className="text-right tabular-nums">
                        {n.toLocaleString()}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function SourcesTab() {
  const sources = useQuery({
    queryKey: ["admin", "jobs-admin", "sources"],
    queryFn: () => unwrap(api.GET("/api/v1/admin/job-sources")),
    refetchInterval: (q) => (q.state.data?.some((s) => s.last_run?.status === "running") ? 3000 : false),
  });
  const [editing, setEditing] = useState<JobSource | null>(null);
  const [history, setHistory] = useState<JobSource | null>(null);
  const invalidate = useInvalidate();
  const toggle = useMutation({
    mutationFn: (s: JobSource) =>
      unwrap(
        api.PATCH("/api/v1/admin/job-sources/{key}", {
          params: { path: { key: s.key } },
          body: { enabled: !s.enabled },
        }),
      ),
    onSuccess: invalidate,
    onError,
  });
  const run = useMutation({
    mutationFn: (key: string) =>
      unwrap(api.POST("/api/v1/admin/job-sources/{key}/run", { params: { path: { key } } })),
    onSuccess: (_, key) => {
      toast.success(`Run started for ${key}. This can take a few minutes.`);
      setTimeout(invalidate, 1500);
    },
    onError,
  });

  if (sources.isError) return <ErrorState error={sources.error} onRetry={() => sources.refetch()} />;
  if (sources.isPending) return <Skeleton className="m-4 h-48" />;
  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Source</TableHead>
            <TableHead>Schedule</TableHead>
            <TableHead>Last run</TableHead>
            <TableHead className="text-right">Active jobs</TableHead>
            <TableHead className="w-48">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sources.data.map((s) => (
            <TableRow key={s.key}>
              <TableCell>
                <p className="font-medium">{s.name}</p>
                {s.not_configured_reason ? (
                  <p className="text-xs text-warning">{s.not_configured_reason}</p>
                ) : s.last_error ? (
                  <p className="max-w-xs truncate text-xs text-destructive" title={s.last_error}>
                    {s.last_error}
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    {s.uses_company_boards ? "Reads the company boards below" : "Aggregator API"}
                  </p>
                )}
              </TableCell>
              <TableCell className="whitespace-nowrap">
                <label className="inline-flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={s.enabled}
                    onChange={() => toggle.mutate(s)}
                    className="size-4 accent-[var(--primary)]"
                  />
                  {s.enabled ? schedule(s.schedule_minutes) : "Disabled"}
                </label>
              </TableCell>
              <TableCell className="whitespace-nowrap">
                <RunBadge run={s.last_run} />
                <span className="ml-2 text-xs text-muted-foreground">{formatDateTime(s.last_run_at)}</span>
                {s.last_run && (
                  <span className="block text-xs text-muted-foreground">
                    +{s.last_run.created} new · {s.last_run.updated} updated · {s.last_run.deactivated}{" "}
                    retired
                  </span>
                )}
              </TableCell>
              <TableCell className="text-right tabular-nums">{s.active_jobs.toLocaleString()}</TableCell>
              <TableCell>
                <div className="flex justify-end gap-1">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={
                      Boolean(s.not_configured_reason) || s.last_run?.status === "running" || run.isPending
                    }
                    onClick={() => run.mutate(s.key)}
                  >
                    {s.last_run?.status === "running" ? <RefreshCw className="animate-spin" /> : <Play />} Run
                    now
                  </Button>
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    aria-label={`${s.name} run history`}
                    onClick={() => setHistory(s)}
                  >
                    <History />
                  </Button>
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    aria-label={`${s.name} settings`}
                    onClick={() => setEditing(s)}
                  >
                    <Settings2 />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {editing && <SourceSettingsDialog source={editing} onClose={() => setEditing(null)} />}
      {history && <RunsDialog source={history} onClose={() => setHistory(null)} />}
    </>
  );
}

// ------------------------------------------------------------------ companies

function AddCompanyDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [ats, setAts] = useState<"greenhouse" | "lever" | "ashby">("greenhouse");
  const [token, setToken] = useState("");
  const invalidate = useInvalidate();
  const add = useMutation({
    mutationFn: () =>
      unwrap(api.POST("/api/v1/admin/companies", { body: { name, ats, board_token: token } })),
    onSuccess: () => {
      toast.success(`${name} added. Its jobs arrive on the next run.`);
      invalidate();
      onClose();
    },
    onError,
  });
  const example = {
    greenhouse: "boards.greenhouse.io/<token>",
    lever: "jobs.lever.co/<token>",
    ashby: "jobs.ashbyhq.com/<token>",
  }[ats];
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a company</DialogTitle>
          <DialogDescription>
            Only companies that publish a public job board on a supported ATS.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="company-name">Company name</Label>
            <Input id="company-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="ats">ATS</Label>
              <NativeSelect id="ats" value={ats} onChange={(e) => setAts(e.target.value as typeof ats)}>
                <option value="greenhouse">Greenhouse</option>
                <option value="lever">Lever</option>
                <option value="ashby">Ashby</option>
              </NativeSelect>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="token">Board token</Label>
              <Input
                id="token"
                value={token}
                onChange={(e) => setToken(e.target.value.trim())}
                placeholder="e.g. stripe"
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            The token is the last part of the board URL: {example}
          </p>
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button onClick={() => add.mutate()} disabled={!name || !token || add.isPending}>
            Add company
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ImportDialog({ onClose }: { onClose: () => void }) {
  const [result, setResult] = useState<CompanyImportResult | null>(null);
  const invalidate = useInvalidate();
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/backend/admin/companies/import", { method: "POST", body: form });
      const body = await response.json();
      if (!response.ok)
        throw new ApiError(
          response.status,
          body?.error?.code ?? "error",
          body?.error?.message ?? "Import failed",
        );
      return body as CompanyImportResult;
    },
    onSuccess: (r) => {
      setResult(r);
      invalidate();
    },
    onError,
  });
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Import companies from CSV</DialogTitle>
          <DialogDescription>
            Columns: <code>name,ats,board_token</code> (optional <code>website</code>). Existing boards are
            updated, not duplicated.
          </DialogDescription>
        </DialogHeader>
        <Input
          type="file"
          accept=".csv,text/csv"
          className="h-auto py-2"
          onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])}
        />
        {result && (
          <div className="rounded-lg bg-muted p-3 text-sm" role="status">
            <p>
              {result.created} added · {result.updated} updated · {result.skipped} skipped
            </p>
            {result.errors.length > 0 && (
              <ul className="mt-2 list-disc pl-5 text-xs text-destructive">
                {result.errors.slice(0, 10).map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        <DialogFooter>
          <DialogClose asChild>
            <Button>Done</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CompaniesTab() {
  const [search, setSearch] = useState("");
  const [ats, setAts] = useState<"" | "greenhouse" | "lever" | "ashby">("");
  const [dialog, setDialog] = useState<"add" | "import" | null>(null);
  const [toDelete, setToDelete] = useState<Company | null>(null);
  const debounced = useDebouncedValue(search.trim());
  const invalidate = useInvalidate();
  const companies = useQuery({
    queryKey: ["admin", "jobs-admin", "companies", debounced, ats],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/companies", {
          params: { query: { search: debounced || undefined, ats: ats || undefined } },
        }),
      ),
    placeholderData: keepPreviousData,
  });
  const toggle = useMutation({
    mutationFn: (c: Company) =>
      unwrap(
        api.PATCH("/api/v1/admin/companies/{company_id}", {
          params: { path: { company_id: c.id } },
          body: { enabled: !c.enabled },
        }),
      ),
    onSuccess: invalidate,
    onError,
  });
  const remove = useMutation({
    mutationFn: (c: Company) =>
      unwrap(api.DELETE("/api/v1/admin/companies/{company_id}", { params: { path: { company_id: c.id } } })),
    onSuccess: () => {
      toast.success("Company removed and its jobs retired");
      setToDelete(null);
      invalidate();
    },
    onError,
  });

  return (
    <>
      <div className="flex flex-col gap-3 border-b p-4 md:flex-row">
        <div className="relative flex-1">
          <Search
            aria-hidden
            className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            aria-label="Search companies"
            placeholder="Search companies"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <NativeSelect
          aria-label="Filter by ATS"
          value={ats}
          onChange={(e) => setAts(e.target.value as typeof ats)}
          className="md:w-40"
        >
          <option value="">All ATS</option>
          <option value="greenhouse">Greenhouse</option>
          <option value="lever">Lever</option>
          <option value="ashby">Ashby</option>
        </NativeSelect>
        <Button variant="outline" onClick={() => setDialog("import")}>
          <Upload /> Import CSV
        </Button>
        <Button onClick={() => setDialog("add")}>
          <Plus /> Add company
        </Button>
      </div>
      {companies.isError ? (
        <ErrorState error={companies.error} onRetry={() => companies.refetch()} />
      ) : companies.isPending ? (
        <Skeleton className="m-4 h-48" />
      ) : companies.data.length === 0 ? (
        <EmptyState title="No companies found" />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Company</TableHead>
              <TableHead>Board</TableHead>
              <TableHead>Last fetched</TableHead>
              <TableHead className="text-right">Jobs</TableHead>
              <TableHead className="w-24">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {companies.data.map((c) => (
              <TableRow key={c.id} className={cn(!c.enabled && "opacity-60")}>
                <TableCell className="font-medium">{c.name}</TableCell>
                <TableCell className="font-mono text-xs">
                  {c.ats}/{c.board_token}
                </TableCell>
                <TableCell className="text-sm">
                  {c.last_error ? (
                    <span className="inline-flex items-center gap-1 text-destructive" title={c.last_error}>
                      <XCircle className="size-3.5" /> {c.last_error}
                    </span>
                  ) : c.last_fetched_at ? (
                    <span className="inline-flex items-center gap-1 text-muted-foreground">
                      <CheckCircle2 className="size-3.5 text-success" /> {formatDateTime(c.last_fetched_at)}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-muted-foreground">
                      <Clock className="size-3.5" /> Not yet
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums">{c.active_jobs.toLocaleString()}</TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <input
                      type="checkbox"
                      aria-label={`${c.enabled ? "Disable" : "Enable"} ${c.name}`}
                      checked={c.enabled}
                      onChange={() => toggle.mutate(c)}
                      className="size-4 self-center accent-[var(--primary)]"
                    />
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      aria-label={`Remove ${c.name}`}
                      onClick={() => setToDelete(c)}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {dialog === "add" && <AddCompanyDialog onClose={() => setDialog(null)} />}
      {dialog === "import" && <ImportDialog onClose={() => setDialog(null)} />}
      {toDelete && (
        <Dialog open onOpenChange={(open) => !open && setToDelete(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Remove {toDelete.name}?</DialogTitle>
              <DialogDescription>
                Its {toDelete.active_jobs} active jobs are retired and disappear from search. You can add the
                company again later.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline">Cancel</Button>
              </DialogClose>
              <Button
                variant="destructive"
                disabled={remove.isPending}
                onClick={() => remove.mutate(toDelete)}
              >
                Remove company
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}

// ------------------------------------------------------------------ jobs

const JOB_STATUSES = [
  { value: "", label: "All jobs" },
  { value: "listed", label: "Listed" },
  { value: "featured", label: "Featured" },
  { value: "hidden", label: "Hidden" },
  { value: "duplicate", label: "Suspected duplicates" },
  { value: "inactive", label: "No longer listed" },
] as const;

function JobsTab() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<(typeof JOB_STATUSES)[number]["value"]>("");
  const [page, setPage] = useState(1);
  const debounced = useDebouncedValue(search.trim());
  const invalidate = useInvalidate();
  const jobs = useQuery({
    queryKey: ["admin", "jobs-admin", "jobs", debounced, status, page],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/jobs", {
          params: {
            query: { search: debounced || undefined, status: status || undefined, page, page_size: 25 },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
  const flags = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { hidden?: boolean; featured?: boolean } }) =>
      unwrap(api.PATCH("/api/v1/admin/jobs/{job_id}", { params: { path: { job_id: id } }, body })),
    onSuccess: invalidate,
    onError,
  });
  const notDuplicate = useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST("/api/v1/admin/jobs/{job_id}/not-duplicate", { params: { path: { job_id: id } } })),
    onSuccess: () => {
      toast.success("Marked as not a duplicate");
      invalidate();
    },
    onError,
  });

  return (
    <>
      <div className="flex flex-col gap-3 border-b p-4 md:flex-row">
        <div className="relative flex-1">
          <Search
            aria-hidden
            className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            aria-label="Search jobs"
            placeholder="Search by title or company"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="pl-9"
          />
        </div>
        <NativeSelect
          aria-label="Filter by status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as typeof status);
            setPage(1);
          }}
          className="md:w-56"
        >
          {JOB_STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </NativeSelect>
      </div>
      {jobs.isError ? (
        <ErrorState error={jobs.error} onRetry={() => jobs.refetch()} />
      ) : jobs.isPending ? (
        <Skeleton className="m-4 h-64" />
      ) : jobs.data.items.length === 0 ? (
        <EmptyState title="No jobs found" />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Job</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden md:table-cell">First seen</TableHead>
                <TableHead className="w-36">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.data.items.map((job) => (
                <TableRow key={job.id}>
                  <TableCell>
                    <p className="font-medium">{job.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {job.company_name} · {job.location ?? "No location"} · {job.source}
                    </p>
                    {job.duplicate_of_title && (
                      <p className="mt-1 text-xs text-warning">
                        <Copy className="mr-1 inline size-3" />
                        Duplicate of {job.duplicate_of_title}
                      </p>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {!job.is_active && <Badge variant="muted">Retired</Badge>}
                      {job.is_hidden && <Badge variant="destructive">Hidden</Badge>}
                      {job.is_featured && <Badge variant="sunrise">Featured</Badge>}
                      {job.is_active && !job.is_hidden && !job.duplicate_of_id && (
                        <Badge variant="success">Listed</Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="hidden text-sm text-muted-foreground md:table-cell">
                    {formatDateTime(job.first_seen_at)}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      {job.duplicate_of_id && (
                        <Button size="sm" variant="outline" onClick={() => notDuplicate.mutate(job.id)}>
                          Not a dupe
                        </Button>
                      )}
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        aria-label={job.is_featured ? "Unfeature" : "Feature"}
                        aria-pressed={job.is_featured}
                        onClick={() => flags.mutate({ id: job.id, body: { featured: !job.is_featured } })}
                      >
                        <Star className={cn(job.is_featured && "fill-sunrise text-sunrise")} />
                      </Button>
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        aria-label={job.is_hidden ? "Unhide" : "Hide"}
                        aria-pressed={job.is_hidden}
                        onClick={() => flags.mutate({ id: job.id, body: { hidden: !job.is_hidden } })}
                      >
                        <EyeOff className={cn(job.is_hidden && "text-destructive")} />
                      </Button>
                      <Button asChild size="icon-sm" variant="ghost" aria-label="Open the original posting">
                        <a href={job.apply_url} target="_blank" rel="noopener noreferrer">
                          <ExternalLink />
                        </a>
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pagination page={page} pageSize={25} total={jobs.data.total} onPageChange={setPage} />
        </>
      )}
    </>
  );
}

// ------------------------------------------------------------------ page

export function JobsAdmin() {
  const [tab, setTab] = useState<Tab>("sources");
  const reindex = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/admin/search/reindex")),
    onSuccess: (r) => toast.success(`Search index rebuilt: ${r.indexed.toLocaleString()} jobs`),
    onError,
  });
  const tabs: { id: Tab; label: string }[] = [
    { id: "sources", label: "Sources" },
    { id: "companies", label: "Companies" },
    { id: "jobs", label: "Jobs" },
  ];
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Jobs & Sources"
        description="Where jobs come from, how often, and what job seekers see. Every change is audited."
        actions={
          <Button variant="outline" size="sm" onClick={() => reindex.mutate()} disabled={reindex.isPending}>
            <RefreshCw className={cn(reindex.isPending && "animate-spin")} /> Rebuild search index
          </Button>
        }
      />
      <div
        role="tablist"
        aria-label="Jobs admin sections"
        className="mb-4 inline-flex rounded-lg border bg-card p-0.5"
      >
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "rounded-md px-4 py-1.5 text-sm font-medium transition-colors",
              tab === t.id
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <Card role="tabpanel">
        {tab === "sources" && <SourcesTab />}
        {tab === "companies" && <CompaniesTab />}
        {tab === "jobs" && <JobsTab />}
      </Card>
    </div>
  );
}
