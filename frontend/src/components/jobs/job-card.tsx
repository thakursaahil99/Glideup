"use client";

import { Bookmark, BookmarkCheck, Building2, Flame, MapPin, Sparkles } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api/client";
import { remoteLabel } from "@/components/jobs/location-filters";
import { MatchBadge } from "@/components/matching/match-badge";
import { useToggleSave } from "@/lib/api/jobs";
import { EXPERIENCE_LEVELS, type JobCard as Job, WORK_MODES } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function postedAgo(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const days = Math.round((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days < 1) return "today";
  if (days < 30) return relative.format(-days, "day");
  const months = Math.round(days / 30);
  return months < 12 ? relative.format(-months, "month") : relative.format(-Math.round(months / 12), "year");
}

export function workModeLabel(mode: Job["work_mode"]) {
  return WORK_MODES.find((m) => m.value === mode)?.label ?? null;
}

export function levelLabel(level: Job["experience_level"]) {
  return EXPERIENCE_LEVELS.find((l) => l.value === level)?.label ?? null;
}

/** "Hiring actively · 42 open roles", or null when the company isn't hiring at scale. */
export function hiringLabel(job: Pick<Job, "hiring_actively" | "company_open_roles" | "company_new_roles_7d">) {
  if (!job.hiring_actively) return null;
  const roles = `${job.company_open_roles} open role${job.company_open_roles === 1 ? "" : "s"}`;
  const fresh = job.company_new_roles_7d > 0 ? `, ${job.company_new_roles_7d} new this week` : "";
  return `Hiring actively · ${roles}${fresh}`;
}

export function HiringBadge({ job }: { job: Parameters<typeof hiringLabel>[0] }) {
  const label = hiringLabel(job);
  if (!label) return null;
  return (
    <Badge variant="sunrise">
      <Flame className="size-3" aria-hidden /> {label}
    </Badge>
  );
}

export function SaveButton({
  job,
  size = "icon-sm",
}: {
  job: Pick<Job, "id" | "is_saved" | "title">;
  size?: "icon-sm" | "default";
}) {
  const toggle = useToggleSave();
  const Icon = job.is_saved ? BookmarkCheck : Bookmark;
  return (
    <Button
      variant={size === "default" ? "outline" : "ghost"}
      size={size}
      aria-pressed={job.is_saved}
      aria-label={job.is_saved ? `Remove ${job.title} from saved jobs` : `Save ${job.title}`}
      onClick={(event) => {
        event.preventDefault();
        toggle.mutate({ id: job.id, saved: !job.is_saved }, { onError: (e) => toast.error(errorMessage(e)) });
      }}
    >
      <Icon className={cn(job.is_saved && "fill-primary text-primary")} />
      {size === "default" && (job.is_saved ? "Saved" : "Save")}
    </Button>
  );
}

export function JobCard({ job }: { job: Job }) {
  const mode = remoteLabel(job) ?? workModeLabel(job.work_mode);
  const level = levelLabel(job.experience_level);
  const posted = postedAgo(job.posted_at ?? job.first_seen_at);
  return (
    <article className="group relative rounded-xl border bg-card p-4 transition-colors hover:border-primary/40 sm:p-5">
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className="inline-flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-sm font-semibold text-primary"
        >
          {job.company_name.slice(0, 1).toUpperCase()}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="leading-snug font-semibold">
            <Link href={`/jobs/${job.id}`} className="after:absolute after:inset-0 hover:text-primary">
              {job.title}
            </Link>
          </h3>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <Building2 className="size-3.5" aria-hidden /> {job.company_name}
            </span>
            {job.location && (
              <span className="inline-flex items-center gap-1">
                <MapPin className="size-3.5" aria-hidden /> {job.location}
              </span>
            )}
          </p>
        </div>
        <div className="relative z-10">
          <SaveButton job={job} />
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {job.match && <MatchBadge match={job.match} />}
        {job.is_featured && (
          <Badge variant="sunrise">
            <Sparkles className="size-3" /> Featured
          </Badge>
        )}
        <HiringBadge job={job} />
        {mode && <Badge variant="default">{mode}</Badge>}
        {level && <Badge variant="outline">{level}</Badge>}
        {job.salary && <Badge variant="success">{job.salary}</Badge>}
        {job.skills.slice(0, 5).map((skill) => (
          <Badge key={skill} variant="muted">
            {skill}
          </Badge>
        ))}
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        {posted && <>Posted {posted}</>}
        {job.attribution && <> · {job.attribution}</>}
      </p>
    </article>
  );
}
