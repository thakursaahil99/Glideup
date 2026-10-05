"use client";

import { ArrowRight, Sparkles } from "lucide-react";
import Link from "next/link";

import { MatchBadge } from "@/components/matching/match-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/primitives";
import { useRecommendations } from "@/lib/api/matches";

/** The three best-fitting jobs right now; hidden until we know the user's skills. */
export function TopMatches() {
  const query = useRecommendations({ india: false, remote: false }, 3);
  const first = query.data?.pages[0];
  if (query.isError || (first && (!first.available || first.items.length === 0))) return null;

  return (
    <Card className="mt-6">
      <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="size-4 text-sunrise" aria-hidden /> Your top matches
          </CardTitle>
          <CardDescription className="mt-1">Real openings that fit your resume best.</CardDescription>
        </div>
        <Button asChild variant="ghost" size="sm">
          <Link href="/jobs/recommended">
            See all <ArrowRight />
          </Link>
        </Button>
      </CardHeader>
      <CardContent>
        {!first ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <ul className="divide-y">
            {first.items.map(({ job }) => (
              <li key={job.id} className="flex items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <Link href={`/jobs/${job.id}`} className="font-medium hover:text-primary">
                    {job.title}
                  </Link>
                  <p className="truncate text-sm text-muted-foreground">
                    {job.company_name}
                    {job.location && ` · ${job.location}`}
                  </p>
                </div>
                {job.match && <MatchBadge match={job.match} />}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
