import { Circle, Flame, Gauge, Target } from "lucide-react";
import type { Metadata } from "next";

import { ResumeCard } from "@/components/dashboard/resume-card";
import { TopMatches } from "@/components/dashboard/top-matches";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/primitives";
import { JOURNEY } from "@/lib/navigation";
import { requireUser } from "@/lib/session";

export const metadata: Metadata = { title: "Dashboard" };

const PHASE_FOR_STEP = [2, 3, 4, 8, 5];

const EMPTY_STATS = [
  { label: "Applications", icon: Target, hint: "Track your first application" },
  { label: "Average interview score", icon: Gauge, hint: "Finish a mock interview to see it" },
  { label: "Practice streak", icon: Flame, hint: "Practice two days in a row" },
];

export default async function DashboardPage() {
  const user = await requireUser("/dashboard");
  const firstName = user.name?.split(" ")[0];

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title={firstName ? `Welcome, ${firstName}` : "Welcome to GlideUp"}
        description="Your flight plan from resume to offer starts here."
      />

      <ResumeCard />
      <TopMatches />

      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        {EMPTY_STATS.map(({ label, icon: Icon, hint }) => (
          <Card key={label}>
            <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
              <CardDescription>{label}</CardDescription>
              <Icon className="size-4 text-muted-foreground" aria-hidden />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold text-muted-foreground/60">—</p>
              <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Your journey</CardTitle>
          <CardDescription>Each step unlocks the next. We&apos;ll guide you through them.</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="divide-y">
            {JOURNEY.map(({ title, body }, index) => {
              return (
                <li key={title} className="flex items-start gap-3 py-3">
                  <Circle
                    className={`mt-0.5 size-5 shrink-0 ${index === 0 ? "text-sunrise" : "text-muted-foreground/50"}`}
                    aria-hidden
                  />
                  <div className="flex-1">
                    <p className="font-medium">{title}</p>
                    <p className="text-sm text-muted-foreground">{body}</p>
                  </div>
                  <Badge variant="muted">Phase {PHASE_FOR_STEP[index]}</Badge>
                </li>
              );
            })}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
