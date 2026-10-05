"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FlaskConical, Pencil, Plus, Trash2, Upload, XCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

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
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { DIFFICULTIES, type Difficulty, type QuestionAdminDetail, type QuestionIn } from "@/lib/api/types";

const KEY = ["admin", "questions"];

/** QuestionIn with its defaulted lists made required, for the editor's state. */
export type QuestionForm = Omit<QuestionIn, "topics" | "templates" | "tests" | "type"> & {
  type: NonNullable<QuestionIn["type"]>;
  topics: string[];
  templates: NonNullable<QuestionIn["templates"]>;
  tests: NonNullable<QuestionIn["tests"]>;
};
const onError = (e: unknown) => toast.error(errorMessage(e));

export const EMPTY_QUESTION: QuestionForm = {
  type: "dsa",
  framework_key: null,
  content: null,
  slug: "",
  title: "",
  difficulty: "easy",
  topics: [],
  statement: "",
  templates: [{ language_key: "python", starter_code: "", reference_solution: "" }],
  tests: [
    { input: "", expected_output: "", hidden: false },
    { input: "", expected_output: "", hidden: true },
  ],
};

export function toInput(q: QuestionAdminDetail): QuestionForm {
  return {
    type: q.type as QuestionForm["type"],
    framework_key: q.framework_key,
    content: q.content,
    slug: q.slug,
    title: q.title,
    difficulty: q.difficulty,
    topics: q.topics,
    statement: q.statement,
    templates: q.templates,
    tests: q.tests,
  };
}

function Languages() {
  const client = useQueryClient();
  const langs = useQuery({
    queryKey: ["admin", "languages"],
    queryFn: () => unwrap(api.GET("/api/v1/admin/languages")),
  });
  const update = useMutation({
    mutationFn: ({
      key,
      body,
    }: {
      key: string;
      body: { enabled?: boolean; time_limit_s?: number; memory_limit_mb?: number };
    }) => unwrap(api.PATCH("/api/v1/admin/languages/{key}", { params: { path: { key } }, body })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["admin", "languages"] }),
    onError,
  });
  if (langs.isPending) return <Skeleton className="h-24" />;
  if (langs.isError) return <ErrorState error={langs.error} onRetry={() => langs.refetch()} />;
  return (
    <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
      {langs.data.map((l) => (
        <div key={l.key} className="flex items-center gap-3 rounded-lg border p-3 text-sm">
          <input
            type="checkbox"
            className="size-4 accent-primary"
            checked={l.enabled}
            aria-label={`${l.name} enabled`}
            onChange={(e) => update.mutate({ key: l.key, body: { enabled: e.target.checked } })}
          />
          <span className="flex-1 font-medium">{l.name}</span>
          <Input
            aria-label={`${l.name} time limit (s)`}
            type="number"
            step={0.5}
            min={0.5}
            max={20}
            className="h-8 w-16"
            defaultValue={l.time_limit_s}
            onBlur={(e) =>
              Number(e.target.value) !== l.time_limit_s &&
              update.mutate({ key: l.key, body: { time_limit_s: Number(e.target.value) } })
            }
          />
          <span className="text-xs text-muted-foreground">s</span>
          <Input
            aria-label={`${l.name} memory (MB)`}
            type="number"
            min={32}
            max={2048}
            className="h-8 w-20"
            defaultValue={l.memory_limit_mb}
            onBlur={(e) =>
              Number(e.target.value) !== l.memory_limit_mb &&
              update.mutate({ key: l.key, body: { memory_limit_mb: Number(e.target.value) } })
            }
          />
          <span className="text-xs text-muted-foreground">MB</span>
        </div>
      ))}
    </div>
  );
}

function Editor({ initial, id, onClose }: { initial: QuestionForm; id: string | null; onClose: () => void }) {
  const client = useQueryClient();
  const [form, setForm] = useState<QuestionForm>(initial);
  const [topics, setTopics] = useState(initial.topics.join(", "));
  const [contentText, setContentText] = useState(() => JSON.stringify(initial.content ?? {}, null, 2));
  const isCoding = form.type === "dsa";
  const save = useMutation({
    mutationFn: () => {
      let content: Record<string, unknown> | null = null;
      if (!isCoding) {
        try {
          content = JSON.parse(contentText) as Record<string, unknown>;
        } catch {
          throw new Error("Content must be valid JSON.");
        }
      }
      const body = {
        ...form,
        content,
        topics: topics
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        tests: isCoding ? form.tests : [],
        templates: isCoding ? form.templates : [],
      };
      return id
        ? unwrap(
            api.PUT("/api/v1/admin/questions/{question_id}", { params: { path: { question_id: id } }, body }),
          )
        : unwrap(api.POST("/api/v1/admin/questions", { body }));
    },
    onSuccess: () => {
      toast.success("Saved. Validate it before publishing.");
      void client.invalidateQueries({ queryKey: KEY });
      onClose();
    },
    onError,
  });
  const set = (patch: Partial<QuestionForm>) => setForm({ ...form, ...patch });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[92dvh] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{id ? "Edit question" : "New question"}</DialogTitle>
          <DialogDescription>
            Programs read stdin and print stdout. Saving a published question moves it back to draft until it
            is validated again.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="q-title">Title</Label>
            <Input id="q-title" value={form.title} onChange={(e) => set({ title: e.target.value })} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="q-diff">Difficulty</Label>
            <NativeSelect
              id="q-diff"
              value={form.difficulty}
              onChange={(e) => set({ difficulty: e.target.value as Difficulty })}
            >
              {DIFFICULTIES.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="q-type">Type</Label>
            <NativeSelect
              id="q-type"
              value={form.type}
              onChange={(e) => set({ type: e.target.value as QuestionForm["type"] })}
            >
              <option value="dsa">Coding problem</option>
              <option value="mcq">MCQ (framework)</option>
              <option value="review">Code review (framework)</option>
              <option value="viva">Viva (framework)</option>
              <option value="project">Mini-project (framework)</option>
            </NativeSelect>
          </div>
          {!isCoding && (
            <div className="space-y-1.5">
              <Label htmlFor="q-fw">Framework key</Label>
              <Input
                id="q-fw"
                value={form.framework_key ?? ""}
                onChange={(e) => set({ framework_key: e.target.value || null })}
                placeholder="react"
              />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="q-slug">Slug</Label>
            <Input
              id="q-slug"
              value={form.slug}
              onChange={(e) => set({ slug: e.target.value })}
              placeholder="two-sum"
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="q-topics">Topics (comma-separated)</Label>
            <Input id="q-topics" value={topics} onChange={(e) => setTopics(e.target.value)} />
          </div>
          <div className="space-y-1.5 sm:col-span-3">
            <Label htmlFor="q-statement">Statement (Markdown)</Label>
            <Textarea
              id="q-statement"
              className="min-h-40"
              value={form.statement}
              onChange={(e) => set({ statement: e.target.value })}
            />
          </div>
        </div>

        {isCoding ? (
          <>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">
                Code per language (reference solutions are never shown to users)
              </legend>
              {form.templates.map((t, i) => (
                <div key={i} className="space-y-2 rounded-lg border p-3">
                  <div className="flex items-center gap-2">
                    <NativeSelect
                      aria-label="Language"
                      className="w-44"
                      value={t.language_key}
                      onChange={(e) =>
                        set({
                          templates: form.templates.map((x, n) =>
                            n === i ? { ...x, language_key: e.target.value } : x,
                          ),
                        })
                      }
                    >
                      {["python", "javascript", "typescript", "java", "cpp", "go"].map((k) => (
                        <option key={k} value={k}>
                          {k}
                        </option>
                      ))}
                    </NativeSelect>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label="Remove language"
                      onClick={() => set({ templates: form.templates.filter((_, n) => n !== i) })}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                  <div className="grid gap-2 md:grid-cols-2">
                    <Textarea
                      aria-label="Starter code (empty = default)"
                      placeholder="Starter code (empty = default skeleton)"
                      className="min-h-28 font-mono text-xs"
                      value={t.starter_code ?? ""}
                      onChange={(e) =>
                        set({
                          templates: form.templates.map((x, n) =>
                            n === i ? { ...x, starter_code: e.target.value } : x,
                          ),
                        })
                      }
                    />
                    <Textarea
                      aria-label="Reference solution"
                      placeholder="Reference solution"
                      className="min-h-28 font-mono text-xs"
                      value={t.reference_solution ?? ""}
                      onChange={(e) =>
                        set({
                          templates: form.templates.map((x, n) =>
                            n === i ? { ...x, reference_solution: e.target.value } : x,
                          ),
                        })
                      }
                    />
                  </div>
                </div>
              ))}
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  set({
                    templates: [
                      ...form.templates,
                      { language_key: "javascript", starter_code: "", reference_solution: "" },
                    ],
                  })
                }
              >
                <Plus /> Add language
              </Button>
            </fieldset>

            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">
                Tests ({form.tests.filter((t) => t.hidden).length} hidden)
              </legend>
              {form.tests.map((t, i) => (
                <div key={i} className="grid gap-2 rounded-lg border p-3 md:grid-cols-[1fr_1fr_auto]">
                  <Textarea
                    aria-label={`Test ${i + 1} input`}
                    placeholder="Input (stdin)"
                    className="min-h-16 font-mono text-xs"
                    value={t.input ?? ""}
                    onChange={(e) =>
                      set({
                        tests: form.tests.map((x, n) => (n === i ? { ...x, input: e.target.value } : x)),
                      })
                    }
                  />
                  <Textarea
                    aria-label={`Test ${i + 1} expected output`}
                    placeholder="Expected output"
                    className="min-h-16 font-mono text-xs"
                    value={t.expected_output ?? ""}
                    onChange={(e) =>
                      set({
                        tests: form.tests.map((x, n) =>
                          n === i ? { ...x, expected_output: e.target.value } : x,
                        ),
                      })
                    }
                  />
                  <div className="flex flex-col gap-2">
                    <label className="flex items-center gap-1.5 text-xs">
                      <input
                        type="checkbox"
                        checked={t.hidden ?? true}
                        onChange={(e) =>
                          set({
                            tests: form.tests.map((x, n) =>
                              n === i ? { ...x, hidden: e.target.checked } : x,
                            ),
                          })
                        }
                      />
                      Hidden
                    </label>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Remove test ${i + 1}`}
                      onClick={() => set({ tests: form.tests.filter((_, n) => n !== i) })}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </div>
              ))}
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  set({ tests: [...form.tests, { input: "", expected_output: "", hidden: true }] })
                }
              >
                <Plus /> Add test
              </Button>
            </fieldset>
          </>
        ) : (
          <div className="space-y-1.5">
            <Label htmlFor="q-content">Content (JSON)</Label>
            <p className="text-xs text-muted-foreground">
              mcq: {"{"}options, answer, explanation{"}"} · review: {"{"}language, code, issues[{"{"}key,
              description, weight{"}"}]{"}"} · viva: {"{"}key_points[]{"}"} · project: {"{"}language, starter,
              requirements[{"{"}key, description, pattern?, weight{"}"}]{"}"}
            </p>
            <Textarea
              id="q-content"
              className="min-h-64 font-mono text-xs"
              value={contentText}
              onChange={(e) => setContentText(e.target.value)}
              spellCheck={false}
            />
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => save.mutate()} disabled={save.isPending || !form.title || !form.slug}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function QuestionBankAdmin() {
  const client = useQueryClient();
  const [status, setStatus] = useState("");
  const [editing, setEditing] = useState<{ id: string | null; initial: QuestionForm } | null>(null);
  const list = useQuery({
    queryKey: [...KEY, status],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/questions", {
          params: { query: { status: (status || undefined) as "draft" | undefined } },
        }),
      ),
  });
  const refresh = () => client.invalidateQueries({ queryKey: KEY });
  const validate = useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.POST("/api/v1/admin/questions/{question_id}/validate", { params: { path: { question_id: id } } }),
      ),
    onSuccess: (q) => {
      if (q.validation?.ok) toast.success("All reference solutions pass every test.");
      else toast.error("Validation failed. Open the question to see why.");
      void refresh();
    },
    onError,
  });
  const setQuestionStatus = useMutation({
    mutationFn: ({ id, value }: { id: string; value: "published" | "archived" | "draft" }) =>
      unwrap(
        api.PATCH("/api/v1/admin/questions/{question_id}/status", {
          params: { path: { question_id: id } },
          body: { status: value },
        }),
      ),
    onSuccess: () => refresh(),
    onError,
  });
  async function edit(id: string) {
    try {
      const q = await unwrap(
        api.GET("/api/v1/admin/questions/{question_id}", { params: { path: { question_id: id } } }),
      );
      setEditing({ id, initial: toInput(q) });
    } catch (e) {
      onError(e);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Question bank"
        description="Coding problems, their tests and reference solutions. Questions are validated in the sandbox before they can be published."
        actions={
          <Button size="sm" onClick={() => setEditing({ id: null, initial: EMPTY_QUESTION })}>
            <Plus /> New question
          </Button>
        }
      />
      <section aria-labelledby="languages-heading">
        <h2 id="languages-heading" className="mb-2 text-lg font-semibold">
          Languages and limits
        </h2>
        <Card>
          <Languages />
        </Card>
      </section>
      <Card>
        <div className="flex items-center gap-3 border-b p-4">
          <Label htmlFor="q-status">Status</Label>
          <NativeSelect
            id="q-status"
            className="w-40"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">All</option>
            <option value="published">Published</option>
            <option value="draft">Draft</option>
            <option value="archived">Archived</option>
          </NativeSelect>
        </div>
        {list.isError ? (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        ) : list.isPending ? (
          <Skeleton className="m-4 h-64" />
        ) : list.data.length === 0 ? (
          <EmptyState title="No questions" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Question</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Validated</TableHead>
                <TableHead>Tests</TableHead>
                <TableHead>Attempts</TableHead>
                <TableHead>Acceptance</TableHead>
                <TableHead className="sr-only">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.data.map((q) => (
                <TableRow key={q.id}>
                  <TableCell>
                    <p className="font-medium">{q.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {q.difficulty} · {q.source} · {q.topics.join(", ")}
                    </p>
                  </TableCell>
                  <TableCell>
                    <Badge variant={q.status === "published" ? "success" : "muted"}>{q.status}</Badge>
                  </TableCell>
                  <TableCell>
                    {q.validated ? (
                      <CheckCircle2 className="size-4 text-success" aria-label="Validated" />
                    ) : (
                      <XCircle className="size-4 text-muted-foreground" aria-label="Not validated" />
                    )}
                  </TableCell>
                  <TableCell>{q.tests}</TableCell>
                  <TableCell>{Number(q.stats?.submissions ?? 0)}</TableCell>
                  <TableCell>
                    {typeof q.stats?.acceptance_rate === "number"
                      ? `${Math.round(q.stats.acceptance_rate * 100)}%`
                      : "—"}
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Edit ${q.title}`}
                      onClick={() => void edit(q.id)}
                    >
                      <Pencil />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Validate ${q.title}`}
                      disabled={validate.isPending}
                      onClick={() => validate.mutate(q.id)}
                    >
                      <FlaskConical />
                    </Button>
                    {q.status !== "published" ? (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Publish ${q.title}`}
                        onClick={() => setQuestionStatus.mutate({ id: q.id, value: "published" })}
                      >
                        <Upload />
                      </Button>
                    ) : (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setQuestionStatus.mutate({ id: q.id, value: "archived" })}
                      >
                        Archive
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
      {editing && <Editor id={editing.id} initial={editing.initial} onClose={() => setEditing(null)} />}
    </div>
  );
}
