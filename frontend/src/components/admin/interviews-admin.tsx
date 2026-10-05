"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Settings2, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Pagination } from "@/components/admin/pagination";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge, Input, Label, NativeSelect, Skeleton, Textarea } from "@/components/ui/primitives";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, ApiError, errorMessage, unwrap } from "@/lib/api/client";
import {
  DIFFICULTIES,
  type Difficulty,
  type InterviewTypeAdmin,
  type InterviewTypeUpdate,
  type RubricCriterion,
} from "@/lib/api/types";
import { formatDateTime } from "@/lib/utils";

const TYPES_KEY = ["admin", "interview-types"];
const onError = (e: unknown) => {
  const details = e instanceof ApiError && Array.isArray(e.details) ? ` ${e.details.join(" ")}` : "";
  toast.error(errorMessage(e) + details);
};

function useUpdateType() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ key, body }: { key: string; body: InterviewTypeUpdate }) =>
      unwrap(api.PATCH("/api/v1/admin/interview-types/{key}", { params: { path: { key } }, body })),
    onSuccess: () => client.invalidateQueries({ queryKey: TYPES_KEY }),
    onError,
  });
}

export function rubricProblems(rubric: RubricCriterion[]): string | null {
  if (rubric.length === 0) return "Add at least one criterion.";
  const keys = rubric.map((c) => c.key);
  if (keys.some((k) => !/^[a-z][a-z0-9_]{1,39}$/.test(k)))
    return "Keys use lower-case letters, digits and underscores, starting with a letter.";
  if (new Set(keys).size !== keys.length) return "Each criterion needs a unique key.";
  if (rubric.some((c) => !c.name.trim())) return "Every criterion needs a name.";
  return null;
}

function TypeDialog({ type, onClose }: { type: InterviewTypeAdmin; onClose: () => void }) {
  const update = useUpdateType();
  const [form, setForm] = useState({
    name: type.name,
    description: type.description,
    duration_minutes: type.duration_minutes,
    question_count: type.question_count,
    max_followups: type.max_followups,
    difficulty: type.difficulty,
  });
  const [rubric, setRubric] = useState<RubricCriterion[]>(type.rubric.map((c) => ({ ...c })));
  const problem = rubricProblems(rubric);

  function setCriterion(index: number, patch: Partial<RubricCriterion>) {
    setRubric(rubric.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90dvh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit {type.name}</DialogTitle>
          <DialogDescription>Applies to interviews started from now on. Changes are audited.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="t-name">Name</Label>
            <Input id="t-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="t-difficulty">Default difficulty</Label>
            <NativeSelect
              id="t-difficulty"
              value={form.difficulty}
              onChange={(e) => setForm({ ...form, difficulty: e.target.value as Difficulty })}
            >
              {DIFFICULTIES.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="t-desc">Description</Label>
            <Textarea
              id="t-desc"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          {(
            [
              ["duration_minutes", "Duration (minutes)", 5, 120],
              ["question_count", "Questions", 1, 10],
              ["max_followups", "Follow-ups per question", 0, 6],
            ] as const
          ).map(([field, label, min, max]) => (
            <div key={field} className="space-y-1.5">
              <Label htmlFor={`t-${field}`}>{label}</Label>
              <Input
                id={`t-${field}`}
                type="number"
                min={min}
                max={max}
                value={form[field]}
                onChange={(e) => setForm({ ...form, [field]: Number(e.target.value) })}
              />
            </div>
          ))}
        </div>

        <fieldset className="mt-2 space-y-2">
          <legend className="mb-1 text-sm font-medium">Scoring rubric (each criterion scored 1–5)</legend>
          {rubric.map((c, i) => (
            <div key={i} className="grid gap-2 rounded-lg border p-3 sm:grid-cols-[9rem_1fr_5rem_auto]">
              <Input aria-label="Key" value={c.key} onChange={(e) => setCriterion(i, { key: e.target.value })} />
              <Input aria-label="Name" value={c.name} onChange={(e) => setCriterion(i, { name: e.target.value })} />
              <Input
                aria-label="Weight"
                type="number"
                step={0.5}
                min={0.1}
                max={5}
                value={c.weight}
                onChange={(e) => setCriterion(i, { weight: Number(e.target.value) })}
              />
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Remove ${c.name || "criterion"}`}
                onClick={() => setRubric(rubric.filter((_, n) => n !== i))}
              >
                <Trash2 />
              </Button>
              <Textarea
                aria-label="What it measures"
                className="sm:col-span-4"
                rows={2}
                value={c.description ?? ""}
                onChange={(e) => setCriterion(i, { description: e.target.value })}
              />
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setRubric([...rubric, { key: "", name: "", description: "", weight: 1 }])}
            disabled={rubric.length >= 10}
          >
            <Plus /> Add criterion
          </Button>
          {problem && (
            <p role="alert" className="text-sm text-destructive">
              {problem}
            </p>
          )}
        </fieldset>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={Boolean(problem) || update.isPending}
            onClick={() =>
              update.mutate(
                { key: type.key, body: { ...form, rubric } },
                {
                  onSuccess: () => {
                    toast.success(`${form.name} updated`);
                    onClose();
                  },
                },
              )
            }
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function TypesSection() {
  const types = useQuery({
    queryKey: TYPES_KEY,
    queryFn: () => unwrap(api.GET("/api/v1/admin/interview-types")),
  });
  const update = useUpdateType();
  const [editing, setEditing] = useState<InterviewTypeAdmin | null>(null);
  if (types.isError) return <ErrorState error={types.error} onRetry={() => types.refetch()} />;
  if (types.isPending) return <Skeleton className="h-48 w-full" />;
  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Type</TableHead>
            <TableHead>Duration</TableHead>
            <TableHead>Questions</TableHead>
            <TableHead>Follow-ups</TableHead>
            <TableHead>Rubric</TableHead>
            <TableHead>Enabled</TableHead>
            <TableHead className="sr-only">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {types.data.map((t) => (
            <TableRow key={t.key}>
              <TableCell>
                <p className="font-medium">{t.name}</p>
                <p className="text-xs text-muted-foreground">
                  {t.key} · {t.difficulty}
                </p>
              </TableCell>
              <TableCell>{t.duration_minutes} min</TableCell>
              <TableCell>{t.question_count}</TableCell>
              <TableCell>{t.max_followups}</TableCell>
              <TableCell className="max-w-64 text-xs text-muted-foreground">
                {t.rubric.map((c) => c.name).join(", ")}
              </TableCell>
              <TableCell>
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={t.enabled}
                  aria-label={`${t.name} enabled`}
                  onChange={(e) => update.mutate({ key: t.key, body: { enabled: e.target.checked } })}
                />
              </TableCell>
              <TableCell className="text-right">
                <Button variant="ghost" size="sm" onClick={() => setEditing(t)}>
                  <Settings2 /> Edit
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {editing && <TypeDialog type={editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function InterviewsSection() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const list = useQuery({
    queryKey: ["admin", "interviews", page, status],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/interviews", {
          params: {
            query: {
              page,
              page_size: 25,
              status: (status || undefined) as "completed" | undefined,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <div className="flex items-center gap-3 border-b p-4">
        <Label htmlFor="status-filter">Status</Label>
        <NativeSelect
          id="status-filter"
          className="w-48"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All</option>
          {["preparing", "ready", "in_progress", "completed", "failed"].map((s) => (
            <option key={s} value={s}>
              {s.replace("_", " ")}
            </option>
          ))}
        </NativeSelect>
      </div>
      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.isPending ? (
        <Skeleton className="m-4 h-48" />
      ) : list.data.items.length === 0 ? (
        <EmptyState title="No interviews yet" />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>User</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Score</TableHead>
                <TableHead>Hints</TableHead>
                <TableHead>Started</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.data.items.map((i) => (
                <TableRow key={i.id}>
                  <TableCell>{i.user_email}</TableCell>
                  <TableCell>
                    {i.type_key}
                    {i.job_title && <span className="block text-xs text-muted-foreground">{i.job_title}</span>}
                  </TableCell>
                  <TableCell>
                    <Badge variant="muted">{i.status.replace("_", " ")}</Badge>
                    {i.end_reason && (
                      <span className="block text-xs text-muted-foreground">{i.end_reason.replace("_", " ")}</span>
                    )}
                  </TableCell>
                  <TableCell>{i.overall_score ?? (i.report_status ? i.report_status : "—")}</TableCell>
                  <TableCell>{i.hints_used}</TableCell>
                  <TableCell className="whitespace-nowrap">{formatDateTime(i.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pagination page={page} pageSize={25} total={list.data.total} onPageChange={setPage} />
        </>
      )}
    </>
  );
}

export function InterviewsAdmin() {
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Interviews"
        description="Interview types, their timing and scoring rubrics, and every interview taken."
      />
      <Card>
        <TypesSection />
      </Card>
      <section aria-labelledby="all-interviews">
        <h2 id="all-interviews" className="mb-3 text-lg font-semibold">
          All interviews
        </h2>
        <Card>
          <InterviewsSection />
        </Card>
      </section>
    </div>
  );
}
