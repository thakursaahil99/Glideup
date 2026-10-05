"use client";

import { Award } from "lucide-react";
import Link from "next/link";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, Skeleton } from "@/components/ui/primitives";
import { useMySkills } from "@/lib/api/skills";

const LEVEL_VARIANT = {
  expert: "success",
  advanced: "default",
  intermediate: "sunrise",
  beginner: "muted",
} as const;

/** Measured skills (from tests, not self-reported) and earned badges. */
export function SkillsCard() {
  const { data, isPending } = useMySkills();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Award className="size-4 text-sunrise" aria-hidden /> Verified skills & badges
        </CardTitle>
        <CardDescription>Measured by your coding problems and framework tests.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : !data || (data.skills.length === 0 && data.badges.length === 0) ? (
          <p className="text-sm text-muted-foreground">
            Nothing yet.{" "}
            <Link href="/tests" className="text-primary hover:underline">
              Take a test
            </Link>{" "}
            to earn your first verified skill.
          </p>
        ) : (
          <>
            <ul className="space-y-3">
              {data.skills.map((s) => (
                <li key={s.skill}>
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium capitalize">
                      {s.skill} <span className="text-xs font-normal text-muted-foreground">({s.kind})</span>
                    </span>
                    <Badge variant={LEVEL_VARIANT[s.level as keyof typeof LEVEL_VARIANT] ?? "muted"}>
                      {s.level} · {s.score}
                    </Badge>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-muted">
                    <div className="h-full rounded-full bg-primary" style={{ width: `${s.score}%` }} />
                  </div>
                </li>
              ))}
            </ul>
            {data.badges.length > 0 && (
              <ul className="flex flex-wrap gap-2" aria-label="Badges">
                {data.badges.map((b) => (
                  <li key={b.key}>
                    <Badge variant="sunrise" title={b.description}>
                      <Award className="size-3" aria-hidden /> {b.name}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
