"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, ShieldCheck, Table2, UserCheck, UserPlus, Users, UserX } from "lucide-react";
import { useState } from "react";

import { SignupsChart } from "@/components/admin/signups-chart";
import { PageHeader } from "@/components/page-header";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/primitives";
import { api, unwrap } from "@/lib/api/client";
import { cn } from "@/lib/utils";

const RANGES = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
] as const;

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

function rangeParams(days: number) {
  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  start.setUTCHours(0, 0, 0, 0);
  return { start: start.toISOString(), end: end.toISOString() };
}

function StatTile({ label, value, icon: Icon }: { label: string; value?: number; icon: typeof Users }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between pb-2">
        <CardDescription>{label}</CardDescription>
        <Icon className="size-4 text-muted-foreground" aria-hidden />
      </CardHeader>
      <CardContent>
        {value === undefined ? (
          <Skeleton className="h-8 w-16" />
        ) : (
          <p className="text-3xl font-semibold">{compact.format(value)}</p>
        )}
      </CardContent>
    </Card>
  );
}

export function AdminOverview() {
  const [days, setDays] = useState<number>(30);
  const [asTable, setAsTable] = useState(false);

  const query = useQuery({
    queryKey: ["admin", "overview", days],
    queryFn: () => unwrap(api.GET("/api/v1/admin/overview", { params: { query: rangeParams(days) } })),
  });
  const data = query.data;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Overview"
        description="Platform health at a glance. More metrics arrive as each module ships."
        actions={
          <div role="group" aria-label="Date range" className="inline-flex rounded-lg border bg-card p-0.5">
            {RANGES.map((r) => (
              <button
                key={r.days}
                type="button"
                aria-pressed={days === r.days}
                onClick={() => setDays(r.days)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  days === r.days
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
        }
      />

      {query.isError ? (
        <Card>
          <ErrorState error={query.error} onRetry={() => query.refetch()} />
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <StatTile label="Total users" value={data?.total_users} icon={Users} />
            <StatTile label="Active (30 days)" value={data?.active_users_30d} icon={UserCheck} />
            <StatTile label={`New (${days} days)`} value={data?.new_users_in_range} icon={UserPlus} />
            <StatTile label="Suspended" value={data?.suspended_users} icon={UserX} />
            <StatTile label="Admins" value={data?.admin_users} icon={ShieldCheck} />
          </div>

          <Card className="mt-6">
            <CardHeader className="flex-row items-start justify-between gap-4">
              <div>
                <CardTitle>Daily sign-ups</CardTitle>
                <CardDescription>New accounts per day (UTC), last {days} days</CardDescription>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setAsTable((v) => !v)}
                aria-label={asTable ? "Show as chart" : "Show as table"}
              >
                {asTable ? <BarChart3 /> : <Table2 />}
                {asTable ? "Chart" : "Table"}
              </Button>
            </CardHeader>
            <CardContent>
              {data ? (
                <SignupsChart data={data.signups_by_day} asTable={asTable} />
              ) : (
                <Skeleton className="h-72 w-full" />
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
