"use client";

import { ArrowRight, CheckCircle2, FileUp } from "lucide-react";
import Link from "next/link";

import { ParseStatus } from "@/components/resume/parse-status";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge, Skeleton } from "@/components/ui/primitives";
import { useActiveResume } from "@/lib/api/hooks";

/** Step 1 of the journey, reflecting the real resume state. */
export function ResumeCard() {
  const { data: resume, isPending } = useActiveResume();

  return (
    <Card className="overflow-hidden">
      <div
        className="grid gap-6 p-6 md:grid-cols-[1fr_auto] md:items-center"
        style={{ background: "var(--sky-gradient)" }}
      >
        {isPending ? (
          <Skeleton className="h-20 w-full md:col-span-2" />
        ) : !resume ? (
          <>
            <div>
              <Badge variant="sunrise">Step 1 of 5</Badge>
              <h2 className="mt-3 text-xl font-semibold">Upload your resume to get started</h2>
              <p className="mt-1 max-w-xl text-sm text-muted-foreground">
                GlideUp reads your resume, extracts your skills and experience, and uses them to match you
                with real jobs and tailor every practice session.
              </p>
            </div>
            <Button asChild variant="sunrise" size="lg">
              <Link href="/onboarding">
                <FileUp /> Upload resume
              </Link>
            </Button>
          </>
        ) : resume.status === "parsed" ? (
          <>
            <div>
              <Badge variant="success">
                <CheckCircle2 className="size-3" /> Resume ready
              </Badge>
              <h2 className="mt-3 text-xl font-semibold">
                {resume.skills.length} skills found
                {resume.parsed?.total_years_experience
                  ? ` · ${resume.parsed.total_years_experience} years of experience`
                  : ""}
              </h2>
              <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Top skills">
                {resume.skills.slice(0, 10).map((s) => (
                  <li key={s.name}>
                    <Badge>{s.name}</Badge>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-sm text-muted-foreground">
                Next: browse real jobs. Match scores for these skills arrive in phase 4.
              </p>
            </div>
            <div className="flex flex-col gap-2">
              <Button asChild variant="sunrise" size="lg">
                <Link
                  href={resume.skills[0] ? `/jobs?q=${encodeURIComponent(resume.skills[0].name)}` : "/jobs"}
                >
                  Find jobs <ArrowRight />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg">
                <Link href="/profile">Review skills</Link>
              </Button>
            </div>
          </>
        ) : (
          <div className="md:col-span-2">
            <Badge variant="sunrise">Step 1 of 5</Badge>
            <h2 className="mt-3 mb-4 text-xl font-semibold">Reading your resume…</h2>
            <ParseStatus resume={resume} />
          </div>
        )}
      </div>
    </Card>
  );
}
