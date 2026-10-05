"use client";

import { Gauge } from "lucide-react";
import Link from "next/link";

import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { useInterviews } from "@/lib/api/interviews";
import type { InterviewSummary } from "@/lib/api/types";

/** Mean of the scored interviews, and the change between the last two. */
export function scoreTrend(items: InterviewSummary[]): { average: number | null; delta: number | null } {
  const scores = items
    .filter((i) => typeof i.overall_score === "number")
    .map((i) => i.overall_score as number); // newest first
  if (!scores.length) return { average: null, delta: null };
  const average = Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
  return { average, delta: scores.length > 1 ? scores[0] - scores[1] : null };
}

export function InterviewScoreCard() {
  const { data } = useInterviews();
  const { average, delta } = scoreTrend(data ?? []);
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardDescription>Average interview score</CardDescription>
        <Gauge className="size-4 text-muted-foreground" aria-hidden />
      </CardHeader>
      <CardContent>
        {average === null ? (
          <>
            <p className="text-2xl font-semibold text-muted-foreground/60">—</p>
            <p className="mt-1 text-xs text-muted-foreground">
              <Link href="/interviews" className="hover:text-primary">
                Finish a mock interview to see it
              </Link>
            </p>
          </>
        ) : (
          <>
            <p className="text-2xl font-semibold">{average}/100</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {delta === null
                ? "From your first interview"
                : delta >= 0
                  ? `Up ${delta} since your previous interview`
                  : `Down ${-delta} since your previous interview`}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
