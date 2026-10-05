"use client";

import { Info, TriangleAlert, X } from "lucide-react";
import { useState } from "react";

import { useAnnouncements } from "@/lib/api/platform";
import { cn } from "@/lib/utils";

const KEY = "glideup:dismissed-announcements";

function readDismissed(): string[] {
  try {
    return JSON.parse(window.localStorage.getItem(KEY) ?? "[]") as string[];
  } catch {
    return [];
  }
}

/** Site-wide notices from Admin → Announcements; each can be dismissed (remembered locally). */
export function AnnouncementBanner() {
  const { data } = useAnnouncements();
  const [dismissed, setDismissed] = useState<string[]>(() => (typeof window === "undefined" ? [] : readDismissed()));
  const visible = (data ?? []).filter((a) => !dismissed.includes(a.id));
  if (!visible.length) return null;

  function dismiss(id: string) {
    const next = [...dismissed, id];
    setDismissed(next);
    try {
      window.localStorage.setItem(KEY, JSON.stringify(next.slice(-50)));
    } catch {
      // storage unavailable: the banner just comes back next visit
    }
  }

  return (
    <div className="space-y-2 px-4 pt-4 sm:px-6 lg:px-8">
      {visible.map((a) => {
        const Icon = a.level === "warning" ? TriangleAlert : Info;
        return (
          <div
            key={a.id}
            role="status"
            className={cn(
              "flex items-start gap-3 rounded-lg border p-3 text-sm",
              a.level === "warning" ? "border-warning/40 bg-warning/10" : "border-primary/30 bg-primary-soft",
            )}
          >
            <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="font-medium">{a.title}</p>
              {a.body && <p className="text-muted-foreground">{a.body}</p>}
            </div>
            <button
              type="button"
              aria-label={`Dismiss: ${a.title}`}
              className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
              onClick={() => dismiss(a.id)}
            >
              <X className="size-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
