import { ArrowRight } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { DashboardInsights } from "@/components/dashboard/dashboard-insights";
import { ResumeCard } from "@/components/dashboard/resume-card";
import { TopMatches } from "@/components/dashboard/top-matches";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { JOURNEY } from "@/lib/navigation";
import { requireUser } from "@/lib/session";

export const metadata: Metadata = { title: "Dashboard" };

const JOURNEY_LINKS = ["/profile", "/jobs/recommended", "/jobs/recommended", "/tracker", "/interviews"];

export default async function DashboardPage() {
  const user = await requireUser("/dashboard");
  const firstName = user.name?.split(" ")[0];

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title={firstName ? `Welcome, ${firstName}` : "Welcome to GlideUp"}
        description="Your flight plan from resume to offer."
      />
      <ResumeCard />
      <DashboardInsights />
      <TopMatches />
      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Your journey</CardTitle>
          <CardDescription>Each step builds on the last.</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="divide-y">
            {JOURNEY.map(({ title, body, icon: Icon }, index) => (
              <li key={title}>
                <Link
                  href={JOURNEY_LINKS[index] ?? "/dashboard"}
                  className="flex items-start gap-3 py-3 transition-colors hover:text-primary"
                >
                  <Icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
                  <span className="flex-1">
                    <span className="block font-medium">{title}</span>
                    <span className="block text-sm text-muted-foreground">{body}</span>
                  </span>
                  <ArrowRight className="mt-0.5 size-4 text-muted-foreground" aria-hidden />
                </Link>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
