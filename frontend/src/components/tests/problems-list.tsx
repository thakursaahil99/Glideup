"use client";

import { CheckCircle2, Circle, CircleDot, Code2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { Card } from "@/components/ui/card";
import { Badge, Skeleton } from "@/components/ui/primitives";
import { useProblems } from "@/lib/api/problems";
import { DIFFICULTIES, type Difficulty } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export const DIFFICULTY_VARIANT = { easy: "success", medium: "default", hard: "sunrise" } as const;

export function ProblemsList({ language }: { language?: string | null }) {
  const [difficulty, setDifficulty] = useState<Difficulty | null>(null);
  const problems = useProblems(difficulty);
  const solved = problems.data?.filter((p) => p.solved).length ?? 0;
  const suffix = language ? `?lang=${encodeURIComponent(language)}` : "";

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Coding tests"
        description="Solve problems in Python, JavaScript, TypeScript, Java, C++ or Go. Your code runs in a sandbox against hidden tests."
      />
      <div className="mb-4 flex flex-wrap items-center gap-2" role="group" aria-label="Difficulty">
        {[{ value: null, label: "All" }, ...DIFFICULTIES].map((d) => (
          <button
            key={d.label}
            type="button"
            aria-pressed={difficulty === d.value}
            onClick={() => setDifficulty(d.value)}
            className={cn(
              "rounded-full border px-3 py-1 text-sm transition-colors",
              difficulty === d.value ? "border-primary bg-primary-soft text-primary" : "hover:bg-accent",
            )}
          >
            {d.label}
          </button>
        ))}
        {problems.data && (
          <span className="ml-auto text-sm text-muted-foreground">
            {solved} of {problems.data.length} solved
          </span>
        )}
      </div>
      {problems.isError ? (
        <Card>
          <ErrorState error={problems.error} onRetry={() => problems.refetch()} />
        </Card>
      ) : problems.isPending ? (
        <Skeleton className="h-80 w-full rounded-xl" />
      ) : problems.data.length === 0 ? (
        <Card>
          <EmptyState icon={<Code2 className="size-5" aria-hidden />} title="No problems yet" />
        </Card>
      ) : (
        <Card>
          <ul className="divide-y">
            {problems.data.map((p) => {
              const Icon = p.solved ? CheckCircle2 : p.attempted ? CircleDot : Circle;
              return (
                <li key={p.slug}>
                  <Link
                    href={`/tests/${p.slug}${suffix}`}
                    className="flex items-center gap-3 p-4 transition-colors hover:bg-accent/50"
                  >
                    <Icon
                      className={cn("size-5 shrink-0", p.solved ? "text-success" : "text-muted-foreground")}
                      aria-label={p.solved ? "Solved" : p.attempted ? "Attempted" : "Not started"}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block font-medium">{p.title}</span>
                      <span className="block truncate text-xs text-muted-foreground">{p.topics.join(" · ")}</span>
                    </span>
                    <Badge variant={DIFFICULTY_VARIANT[p.difficulty]}>{p.difficulty}</Badge>
                  </Link>
                </li>
              );
            })}
          </ul>
        </Card>
      )}
    </div>
  );
}
