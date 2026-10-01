"use client";

import { AlertCircle, CheckCircle2, Loader2, RotateCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api/client";
import { useResumeAction } from "@/lib/api/hooks";
import type { Resume } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const STEPS = [
  { key: "uploaded", label: "Uploaded" },
  { key: "parsing", label: "Reading & extracting skills" },
  { key: "parsed", label: "Ready" },
] as const;

function stepIndex(status: Resume["status"]) {
  return status === "uploaded" ? 0 : status === "parsing" ? 1 : 2;
}

/** Live progress for a resume while the background job parses it. */
export function ParseStatus({ resume }: { resume: Pick<Resume, "id" | "status" | "error" | "parsed_by"> }) {
  const reparse = useResumeAction("reparse");

  if (resume.status === "failed") {
    return (
      <div
        role="alert"
        className="flex flex-col gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-4 sm:flex-row sm:items-center"
      >
        <AlertCircle className="size-5 shrink-0 text-destructive" aria-hidden />
        <p className="flex-1 text-sm">{resume.error ?? "We couldn't parse this resume."}</p>
        <Button
          variant="outline"
          size="sm"
          disabled={reparse.isPending}
          onClick={() => reparse.mutate(resume.id, { onError: (e) => toast.error(errorMessage(e)) })}
        >
          <RotateCw /> Try again
        </Button>
      </div>
    );
  }

  const current = stepIndex(resume.status);
  return (
    <div aria-live="polite">
      <ol className="flex flex-col gap-2 sm:flex-row sm:gap-6">
        {STEPS.map((step, index) => {
          const done = index < current || resume.status === "parsed";
          const active = index === current && resume.status !== "parsed";
          return (
            <li key={step.key} className="flex items-center gap-2 text-sm">
              {done ? (
                <CheckCircle2 className="size-4 text-success" aria-hidden />
              ) : active ? (
                <Loader2 className="size-4 animate-spin text-primary" aria-hidden />
              ) : (
                <span className="size-4 rounded-full border-2 border-muted-foreground/30" aria-hidden />
              )}
              <span className={cn(done || active ? "text-foreground" : "text-muted-foreground")}>
                {step.label}
              </span>
            </li>
          );
        })}
      </ol>
      {resume.status !== "parsed" && (
        <p className="mt-2 text-xs text-muted-foreground">
          This usually takes 10–60 seconds with a local model. You can leave this page; we&apos;ll keep going.
        </p>
      )}
      {resume.status === "parsed" && resume.parsed_by?.startsWith("mock") && (
        <p className="mt-2 text-xs text-warning">
          Parsed with the offline fallback (no AI model was reachable). Review the skills, or try again later
          for a richer result.
        </p>
      )}
    </div>
  );
}
