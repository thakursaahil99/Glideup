"use client";

import { ClipboardCheck, ClipboardPlus } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ApiError, errorMessage } from "@/lib/api/client";
import { useApplications, useCreateApplication } from "@/lib/api/tracker";

/** "Track" on a job: adds it to the application tracker (once). */
export function TrackButton({ jobId }: { jobId: string }) {
  const apps = useApplications();
  const create = useCreateApplication();
  const tracked = apps.data?.find((a) => a.job_id === jobId);
  if (tracked) {
    return (
      <Button asChild variant="outline" size="default">
        <Link href="/tracker">
          <ClipboardCheck /> Tracked · {tracked.status}
        </Link>
      </Button>
    );
  }
  return (
    <Button
      variant="outline"
      disabled={create.isPending}
      onClick={() =>
        create.mutate(
          { job_id: jobId, status: "saved" },
          {
            onSuccess: () => toast.success("Added to your tracker"),
            onError: (e) =>
              e instanceof ApiError && e.code === "already_tracked"
                ? toast.info("Already in your tracker")
                : toast.error(errorMessage(e)),
          },
        )
      }
    >
      <ClipboardPlus /> Track
    </Button>
  );
}
