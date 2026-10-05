"use client";

import { Clock, Layers, Loader2, Play } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge, Skeleton } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api/client";
import { useFrameworks, useStartAttempt } from "@/lib/api/skills";

/** Framework test cards (React, FastAPI, ...) shown above the coding problems. */
export function FrameworkTests() {
  const router = useRouter();
  const frameworks = useFrameworks();
  const start = useStartAttempt();
  if (frameworks.isError) return null;

  return (
    <section aria-labelledby="framework-heading" className="mb-8">
      <h2 id="framework-heading" className="mb-3 text-lg font-semibold">
        Framework tests
      </h2>
      {frameworks.isPending ? (
        <Skeleton className="h-36 w-full rounded-xl" />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {frameworks.data.map((f) => (
            <Card key={f.key} className="flex flex-col gap-3 p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-semibold">{f.name}</p>
                  <p className="text-sm text-muted-foreground">{f.description}</p>
                </div>
                {f.best_score !== null && f.best_score !== undefined && (
                  <Badge variant={f.best_score >= 60 ? "success" : "muted"}>Best {f.best_score}</Badge>
                )}
              </div>
              <p className="flex gap-4 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1">
                  <Clock className="size-3.5" aria-hidden /> {f.duration_minutes} min
                </span>
                <span className="inline-flex items-center gap-1">
                  <Layers className="size-3.5" aria-hidden /> MCQ, code review, viva, mini-project
                </span>
              </p>
              <Button
                className="mt-auto self-start"
                variant="sunrise"
                size="sm"
                disabled={start.isPending || f.questions === 0}
                onClick={() =>
                  start.mutate(f.key, {
                    onSuccess: (attempt) => router.push(`/tests/attempts/${attempt.id}`),
                    onError: (e) => toast.error(errorMessage(e)),
                  })
                }
              >
                {start.isPending && start.variables === f.key ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <Play />
                )}
                {f.best_score !== null && f.best_score !== undefined ? "Take again" : "Start test"}
              </Button>
            </Card>
          ))}
        </div>
      )}
    </section>
  );
}
