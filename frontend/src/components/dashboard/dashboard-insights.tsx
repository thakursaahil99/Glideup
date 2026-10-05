"use client";

import { ArrowRight, Bell, ClipboardList, Code2, Flame, Target } from "lucide-react";
import Link from "next/link";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { InterviewScoreCard } from "@/components/dashboard/interview-score-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, Skeleton } from "@/components/ui/primitives";
import { useDashboard } from "@/lib/api/tracker";
import { APPLICATION_COLUMNS, type DashboardData } from "@/lib/api/types";
import { formatDateTime } from "@/lib/utils";

const shortDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });
const AXIS = { fill: "var(--muted-foreground)", fontSize: 12 };

type TipProps = { active?: boolean; payload?: { payload: Record<string, unknown> }[] };

function Tip({ active, payload, render }: TipProps & { render: (p: Record<string, unknown>) => string[] }) {
  if (!active || !payload?.length) return null;
  const [title, value] = render(payload[0].payload);
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="text-muted-foreground">{title}</p>
      <p className="mt-0.5 flex items-center gap-2 font-medium text-foreground">
        <span aria-hidden className="size-2 rounded-sm bg-chart-1" />
        {value}
      </p>
    </div>
  );
}

function Stat({ label, value, hint, icon: Icon }: { label: string; value: string; hint: string; icon: typeof Target }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardDescription>{label}</CardDescription>
        <Icon className="size-4 text-muted-foreground" aria-hidden />
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold">{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}

function Trend({ data }: { data: DashboardData["interview_trend"] }) {
  if (data.length < 2)
    return <p className="text-sm text-muted-foreground">Finish two interviews to see your trend.</p>;
  const points = data.map((p) => ({ ...p, label: shortDate.format(new Date(String(p.date))) }));
  return (
    <figure aria-label="Interview score over time" className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="label" tickLine={false} axisLine={false} tick={AXIS} />
          <YAxis domain={[0, 100]} tickLine={false} axisLine={false} tick={AXIS} width={40} />
          <Tooltip
            content={<Tip render={(p) => [`${p.label} · ${String(p.type)}`, `${String(p.score)}/100`]} />}
            cursor={{ stroke: "var(--muted-foreground)", strokeDasharray: "3 3" }}
          />
          <Line type="monotone" dataKey="score" stroke="var(--chart-1)" strokeWidth={2} dot={{ r: 4 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </figure>
  );
}

function Skills({ data }: { data: DashboardData["skills"] }) {
  if (data.length < 3)
    return (
      <p className="text-sm text-muted-foreground">
        Your skill radar appears after 3 verified skills.{" "}
        <Link href="/tests" className="text-primary hover:underline">
          Take a test
        </Link>
        .
      </p>
    );
  return (
    <figure aria-label="Verified skill scores" className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} outerRadius="70%">
          <PolarGrid stroke="var(--border)" />
          <PolarAngleAxis dataKey="skill" tick={AXIS} />
          <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
          <Tooltip content={<Tip render={(p) => [String(p.skill), `${String(p.score)} · ${String(p.level)}`]} />} />
          <Radar dataKey="score" stroke="var(--chart-1)" fill="var(--chart-1)" fillOpacity={0.25} strokeWidth={2} isAnimationActive={false} />
        </RadarChart>
      </ResponsiveContainer>
    </figure>
  );
}

function Pipeline({ data }: { data: DashboardData["applications"] }) {
  const rows = APPLICATION_COLUMNS.map((c) => ({ label: c.label, count: data[c.status] ?? 0 }));
  if (!rows.some((r) => r.count))
    return (
      <p className="text-sm text-muted-foreground">
        Track jobs to see your pipeline.{" "}
        <Link href="/jobs/recommended" className="text-primary hover:underline">
          Find jobs
        </Link>
        .
      </p>
    );
  return (
    <figure aria-label="Applications by status" className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 16, left: 8, bottom: 0 }}>
          <CartesianGrid horizontal={false} stroke="var(--border)" />
          <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} tick={AXIS} />
          <YAxis type="category" dataKey="label" tickLine={false} axisLine={false} tick={AXIS} width={90} />
          <Tooltip content={<Tip render={(p) => [String(p.label), `${String(p.count)} applications`]} />} cursor={{ fill: "var(--muted)", opacity: 0.6 }} />
          <Bar dataKey="count" fill="var(--chart-1)" radius={[0, 4, 4, 0]} maxBarSize={18} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}

export function DashboardInsights() {
  const { data, isPending } = useDashboard();
  if (isPending || !data) return <Skeleton className="mt-6 h-96 w-full rounded-xl" />;
  return (
    <div className="mt-6 space-y-6">
      <Card className="flex flex-wrap items-center gap-4 border-primary/30 bg-primary-soft/40 p-5">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium tracking-wide text-primary uppercase">Recommended next step</p>
          <p className="mt-1 text-lg font-semibold">{data.next_step.title}</p>
          <p className="text-sm text-muted-foreground">{data.next_step.body}</p>
        </div>
        <Button asChild variant="sunrise">
          <Link href={data.next_step.href}>
            Go <ArrowRight />
          </Link>
        </Button>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Applications" value={String(data.totals.applications)} hint={`${data.applications.interviewing ?? 0} interviewing · ${data.applications.offer ?? 0} offers`} icon={ClipboardList} />
        <InterviewScoreCard />
        <Stat label="Problems solved" value={String(data.totals.problems_solved)} hint={`${data.totals.tests} framework tests taken`} icon={Code2} />
        <Stat
          label="Practice streak"
          value={`${data.streak_days} day${data.streak_days === 1 ? "" : "s"}`}
          hint={data.active_today ? "You practised today" : "Practise today to keep it going"}
          icon={Flame}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Interview score trend</CardTitle>
          </CardHeader>
          <CardContent>
            <Trend data={data.interview_trend} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Skill radar</CardTitle>
          </CardHeader>
          <CardContent>
            <Skills data={data.skills} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Applications by status</CardTitle>
          </CardHeader>
          <CardContent>
            <Pipeline data={data.applications} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Weak topics</CardTitle>
            <CardDescription>From your recent interviews and tests.</CardDescription>
          </CardHeader>
          <CardContent>
            {data.weak_topics.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nothing stands out yet. Keep practising.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {data.weak_topics.map((t) => (
                  <li key={String(t.topic)} className="flex items-center justify-between gap-2">
                    <span>{String(t.topic)}</span>
                    <Badge variant="muted">
                      {String(t.source)} · {String(t.score)}%
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {data.reminders.length > 0 && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="flex items-center gap-2">
              <Bell className="size-4 text-sunrise" aria-hidden /> Upcoming reminders
            </CardTitle>
            <Button asChild variant="ghost" size="sm">
              <Link href="/tracker">
                Tracker <ArrowRight />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {data.reminders.map((r) => (
                <li key={r.id} className="flex justify-between gap-2">
                  <span>{r.title}</span>
                  <span className="text-muted-foreground">{formatDateTime(r.due_at)}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
