"use client";

import { FileUp, Loader2 } from "lucide-react";
import { useId, useRef, useState, type DragEvent } from "react";

import { errorMessage } from "@/lib/api/client";
import { useUploadResume } from "@/lib/api/hooks";
import type { Resume } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const MAX_MB = 5;

/** Client-side checks give instant feedback; the API re-validates everything. */
export function validateResumeFile(file: File): string | null {
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) return "Please choose a PDF file.";
  if (file.size > MAX_MB * 1024 * 1024) return `The file is larger than ${MAX_MB} MB.`;
  if (file.size === 0) return "That file is empty.";
  return null;
}

export function ResumeDropzone({
  onUploaded,
  compact = false,
}: {
  onUploaded?: (resume: Resume) => void;
  compact?: boolean;
}) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const upload = useUploadResume();

  function handle(file: File | undefined) {
    if (!file) return;
    const problem = validateResumeFile(file);
    setError(problem);
    if (problem) return;
    upload.mutate(file, {
      onSuccess: (resume) => onUploaded?.(resume),
      onError: (e) => setError(errorMessage(e)),
    });
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    handle(event.dataTransfer.files[0]);
  }

  return (
    <div>
      <label
        htmlFor={inputId}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 text-center transition-colors",
          compact ? "py-6" : "py-12",
          dragging
            ? "border-primary bg-primary-soft"
            : "border-input hover:border-primary/60 hover:bg-accent/50",
          upload.isPending && "pointer-events-none opacity-70",
        )}
      >
        <span className="inline-flex size-12 items-center justify-center rounded-full bg-primary-soft text-primary">
          {upload.isPending ? (
            <Loader2 className="size-6 animate-spin" aria-hidden />
          ) : (
            <FileUp className="size-6" aria-hidden />
          )}
        </span>
        <span className="font-medium">
          {upload.isPending ? "Uploading…" : "Drop your resume here, or click to choose"}
        </span>
        <span className="text-sm text-muted-foreground">PDF, up to {MAX_MB} MB and 10 pages</span>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          onChange={(e) => {
            handle(e.target.files?.[0]);
            e.target.value = ""; // allow choosing the same file again after an error
          }}
        />
      </label>
      {error && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
