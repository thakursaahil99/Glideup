"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type Point = { date: string; count: number };

const shortDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
const longDate = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

const fmtShort = (iso: string) => shortDate.format(new Date(`${iso}T00:00:00Z`));
const fmtLong = (iso: string) => longDate.format(new Date(`${iso}T00:00:00Z`));

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="text-muted-foreground">{fmtLong(point.date)}</p>
      <p className="mt-0.5 flex items-center gap-2 font-medium text-foreground">
        <span aria-hidden className="size-2 rounded-sm bg-chart-1" />
        {point.count} new {point.count === 1 ? "user" : "users"}
      </p>
    </div>
  );
}

/** Daily sign-ups: one series, so no legend — the card title names it. */
export function SignupsChart({ data, asTable }: { data: Point[]; asTable: boolean }) {
  if (asTable) {
    return (
      <div className="max-h-72 overflow-y-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead className="text-right">New users</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {[...data].reverse().map((p) => (
              <TableRow key={p.date}>
                <TableCell>{fmtLong(p.date)}</TableCell>
                <TableCell className="text-right tabular-nums">{p.count}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  }

  const total = data.reduce((sum, p) => sum + p.count, 0);
  const peak = data.reduce((max, p) => (p.count > max.count ? p : max), data[0] ?? { date: "", count: 0 });
  const summary = `${total} sign-ups over ${data.length} days${peak.count ? `, peaking at ${peak.count} on ${fmtLong(peak.date)}` : ""}.`;

  return (
    <figure role="img" aria-label={`Bar chart of daily sign-ups. ${summary}`} className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }} barCategoryGap={2}>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeWidth={1} />
          <XAxis
            dataKey="date"
            tickFormatter={fmtShort}
            tickLine={false}
            axisLine={{ stroke: "var(--chart-grid)" }}
            tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
            minTickGap={24}
          />
          <YAxis
            allowDecimals={false}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
            width={48}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--muted)", opacity: 0.6 }} />
          <Bar
            dataKey="count"
            fill="var(--chart-1)"
            radius={[4, 4, 0, 0]}
            maxBarSize={24}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}
