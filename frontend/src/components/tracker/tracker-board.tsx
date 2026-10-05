"use client";

import { Bell, Building2, Check, ExternalLink, MapPin, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState, type DragEvent } from "react";
import { toast } from "sonner";

import { postedAgo } from "@/components/jobs/job-card";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge, Input, Label, NativeSelect, Skeleton, Textarea } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api/client";
import {
  useApplications,
  useCreateApplication,
  useCreateReminder,
  useDeleteApplication,
  useReminders,
  useUpdateApplication,
  useUpdateReminder,
} from "@/lib/api/tracker";
import { type Application, APPLICATION_COLUMNS, type ApplicationStatus } from "@/lib/api/types";
import { cn, formatDateTime } from "@/lib/utils";

const onError = (e: unknown) => toast.error(errorMessage(e));

/** Group into columns, ordered by position (then age). */
export function groupByStatus(apps: Application[]): Record<ApplicationStatus, Application[]> {
  const columns = Object.fromEntries(APPLICATION_COLUMNS.map((c) => [c.status, [] as Application[]])) as Record<
    ApplicationStatus,
    Application[]
  >;
  for (const app of apps) columns[app.status]?.push(app);
  for (const list of Object.values(columns)) {
    list.sort((a, b) => a.position - b.position || a.created_at.localeCompare(b.created_at));
  }
  return columns;
}

function CardItem({ app, onOpen }: { app: Application; onOpen: () => void }) {
  const update = useUpdateApplication();
  return (
    <li
      draggable
      onDragStart={(e: DragEvent<HTMLLIElement>) => e.dataTransfer.setData("text/plain", app.id)}
      className="cursor-grab rounded-lg border bg-card p-3 text-sm shadow-xs active:cursor-grabbing"
    >
      <button type="button" className="block w-full text-left" onClick={onOpen}>
        <span className="block font-medium hover:text-primary">{app.title}</span>
        <span className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
          <Building2 className="size-3" aria-hidden /> {app.company}
        </span>
        {app.location && (
          <span className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
            <MapPin className="size-3" aria-hidden /> {app.location}
          </span>
        )}
        <span className="mt-1 block text-xs text-muted-foreground">Updated {postedAgo(app.updated_at)}</span>
      </button>
      {/* Keyboard / screen-reader path for moving a card. */}
      <NativeSelect
        aria-label={`Move ${app.title} at ${app.company}`}
        className="mt-2 h-8 text-xs"
        value={app.status}
        onChange={(e) => update.mutate({ id: app.id, status: e.target.value as ApplicationStatus }, { onError })}
      >
        {APPLICATION_COLUMNS.map((c) => (
          <option key={c.status} value={c.status}>
            {c.label}
          </option>
        ))}
      </NativeSelect>
    </li>
  );
}

function AddDialog({ onClose }: { onClose: () => void }) {
  const create = useCreateApplication();
  const [form, setForm] = useState({ company: "", title: "", url: "", location: "", status: "applied" as ApplicationStatus });
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add an application</DialogTitle>
          <DialogDescription>For jobs you found outside GlideUp. Jobs from the board have a Track button.</DialogDescription>
        </DialogHeader>
        {(["company", "title", "url", "location"] as const).map((field) => (
          <div key={field} className="space-y-1.5">
            <Label htmlFor={`a-${field}`} className="capitalize">
              {field === "url" ? "Job link" : field}
            </Label>
            <Input id={`a-${field}`} value={form[field]} onChange={(e) => setForm({ ...form, [field]: e.target.value })} />
          </div>
        ))}
        <div className="space-y-1.5">
          <Label htmlFor="a-status">Status</Label>
          <NativeSelect id="a-status" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as ApplicationStatus })}>
            {APPLICATION_COLUMNS.map((c) => (
              <option key={c.status} value={c.status}>
                {c.label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!form.company.trim() || !form.title.trim() || create.isPending}
            onClick={() =>
              create.mutate(
                { company: form.company, title: form.title, url: form.url || undefined, location: form.location || undefined, status: form.status },
                { onSuccess: onClose, onError },
              )
            }
          >
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DetailDialog({ app, onClose }: { app: Application; onClose: () => void }) {
  const update = useUpdateApplication();
  const remove = useDeleteApplication();
  const createReminder = useCreateReminder();
  const [notes, setNotes] = useState(app.notes ?? "");
  const [salary, setSalary] = useState(app.salary ?? "");
  const [note, setNote] = useState("");
  const [reminder, setReminder] = useState({ title: `Follow up with ${app.company}`, due: "" });
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90dvh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{app.title}</DialogTitle>
          <DialogDescription>
            {app.company}
            {app.url && (
              <>
                {" · "}
                <a href={app.url} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 text-primary hover:underline">
                  Job posting <ExternalLink className="size-3" />
                </a>
              </>
            )}
            {app.job_id && (
              <>
                {" · "}
                <Link href={`/jobs/${app.job_id}`} className="text-primary hover:underline">
                  Match & practice
                </Link>
              </>
            )}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="d-salary">Salary / offer</Label>
            <Input id="d-salary" value={salary} onChange={(e) => setSalary(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="d-status">Status</Label>
            <NativeSelect
              id="d-status"
              value={app.status}
              onChange={(e) => update.mutate({ id: app.id, status: e.target.value as ApplicationStatus }, { onError })}
            >
              {APPLICATION_COLUMNS.map((c) => (
                <option key={c.status} value={c.status}>
                  {c.label}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="d-notes">Notes</Label>
            <Textarea id="d-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="self-start"
          onClick={() => update.mutate({ id: app.id, notes, salary }, { onSuccess: () => toast.success("Saved"), onError })}
        >
          <Check /> Save details
        </Button>

        <section aria-label="Timeline" className="space-y-2">
          <h3 className="text-sm font-medium">Timeline</h3>
          <ol className="space-y-1 border-l pl-3 text-sm">
            {app.events.map((e, i) => (
              <li key={i}>
                <span className="text-xs text-muted-foreground">{formatDateTime(e.created_at)} · </span>
                {e.kind === "created"
                  ? `Added as ${e.to_status}`
                  : e.kind === "status"
                    ? `Moved from ${e.from_status} to ${e.to_status}`
                    : e.note}
              </li>
            ))}
          </ol>
          <div className="flex gap-2">
            <Input aria-label="Add a note" placeholder="Add a note (e.g. recruiter call went well)" value={note} onChange={(e) => setNote(e.target.value)} />
            <Button
              size="sm"
              disabled={!note.trim()}
              onClick={() => update.mutate({ id: app.id, note }, { onSuccess: () => setNote(""), onError })}
            >
              Add
            </Button>
          </div>
        </section>

        <section aria-label="Reminder" className="space-y-2">
          <h3 className="text-sm font-medium">Set a reminder</h3>
          <div className="flex flex-wrap gap-2">
            <Input aria-label="Reminder" className="min-w-48 flex-1" value={reminder.title} onChange={(e) => setReminder({ ...reminder, title: e.target.value })} />
            <Input aria-label="When" type="datetime-local" className="w-56" value={reminder.due} onChange={(e) => setReminder({ ...reminder, due: e.target.value })} />
            <Button
              size="sm"
              variant="outline"
              disabled={!reminder.due || !reminder.title.trim()}
              onClick={() =>
                createReminder.mutate(
                  { title: reminder.title, due_at: new Date(reminder.due).toISOString(), application_id: app.id },
                  { onSuccess: () => toast.success("Reminder set. We'll email you when it's due."), onError },
                )
              }
            >
              <Bell /> Remind me
            </Button>
          </div>
        </section>

        <DialogFooter>
          <Button
            variant="ghost"
            className="mr-auto text-destructive"
            onClick={() => remove.mutate(app.id, { onSuccess: onClose, onError })}
          >
            <Trash2 /> Remove
          </Button>
          <Button onClick={onClose}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Reminders() {
  const reminders = useReminders();
  const update = useUpdateReminder();
  const [now] = useState(() => Date.now()); // fixed per mount; enough to flag overdue
  if (!reminders.data || reminders.data.length === 0) return null;
  return (
    <Card className="mb-4 p-4">
      <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <Bell className="size-4 text-sunrise" aria-hidden /> Reminders
      </h2>
      <ul className="space-y-1 text-sm">
        {reminders.data.map((r) => {
          const overdue = new Date(r.due_at).getTime() < now;
          return (
            <li key={r.id} className="flex items-center gap-2">
              <input
                type="checkbox"
                aria-label={`Done: ${r.title}`}
                className="size-4 accent-primary"
                checked={r.done}
                onChange={(e) => update.mutate({ id: r.id, done: e.target.checked }, { onError })}
              />
              <span className="flex-1">{r.title}</span>
              <span className={cn("text-xs", overdue ? "text-destructive" : "text-muted-foreground")}>
                {overdue ? "Overdue · " : ""}
                {formatDateTime(r.due_at)}
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

export function TrackerBoard() {
  const apps = useApplications();
  const update = useUpdateApplication();
  const [adding, setAdding] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [over, setOver] = useState<ApplicationStatus | null>(null);
  const columns = groupByStatus(apps.data ?? []);
  const open = apps.data?.find((a) => a.id === openId) ?? null;

  function drop(status: ApplicationStatus, event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setOver(null);
    const id = event.dataTransfer.getData("text/plain");
    const app = apps.data?.find((a) => a.id === id);
    if (app && app.status !== status) update.mutate({ id, status }, { onError });
  }

  return (
    <div className="mx-auto max-w-[96rem]">
      <PageHeader
        title="Application tracker"
        description="Every application in one place. Drag cards between columns, or use the Move menu."
        actions={
          <Button size="sm" onClick={() => setAdding(true)}>
            <Plus /> Add application
          </Button>
        }
      />
      <Reminders />
      {apps.isError ? (
        <Card>
          <ErrorState error={apps.error} onRetry={() => apps.refetch()} />
        </Card>
      ) : apps.isPending ? (
        <Skeleton className="h-96 w-full rounded-xl" />
      ) : apps.data.length === 0 ? (
        <Card>
          <EmptyState
            title="No applications yet"
            body={
              <>
                Click <span className="font-medium">Track</span> on any job, or{" "}
                <button type="button" className="text-primary hover:underline" onClick={() => setAdding(true)}>
                  add one you found elsewhere
                </button>
                .
              </>
            }
          />
        </Card>
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-4">
          {APPLICATION_COLUMNS.map((column) => (
            <section
              key={column.status}
              aria-label={column.label}
              onDragOver={(e) => {
                e.preventDefault();
                setOver(column.status);
              }}
              onDragLeave={() => setOver(null)}
              onDrop={(e) => drop(column.status, e)}
              className={cn(
                "w-64 shrink-0 rounded-xl border bg-muted/40 p-2 transition-colors",
                over === column.status && "border-primary bg-primary-soft",
              )}
            >
              <h2 className="mb-2 flex items-center justify-between px-1 text-sm font-semibold">
                {column.label}
                <Badge variant="muted">{columns[column.status].length}</Badge>
              </h2>
              <ul className="min-h-16 space-y-2">
                {columns[column.status].map((app) => (
                  <CardItem key={app.id} app={app} onOpen={() => setOpenId(app.id)} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
      {adding && <AddDialog onClose={() => setAdding(false)} />}
      {open && <DetailDialog key={open.id} app={open} onClose={() => setOpenId(null)} />}
    </div>
  );
}
