"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Download, ScrollText } from "lucide-react";
import { Fragment, useState } from "react";

import { Pagination } from "@/components/admin/pagination";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge, Input, NativeSelect, Skeleton } from "@/components/ui/primitives";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, unwrap } from "@/lib/api/client";
import type { AuditLog } from "@/lib/api/types";
import { downloadCsv } from "@/lib/csv";
import { useDebouncedValue } from "@/lib/hooks";
import { cn, formatDateTime } from "@/lib/utils";

const PAGE_SIZE = 50;

/** Known actions; the filter is a prefix match, so "user." selects every user action. */
const ACTION_OPTIONS = [
  { value: "", label: "All actions" },
  { value: "user.", label: "All user actions" },
  { value: "user.role_granted", label: "Role granted (allowlist)" },
  { value: "user.role_changed", label: "Role changed" },
  { value: "user.suspended", label: "User suspended" },
  { value: "user.unsuspended", label: "User unsuspended" },
];

type Json = Record<string, unknown> | null | undefined;

export function diffKeys(before: Json, after: Json) {
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})])).sort();
  return keys.map((key) => {
    const a = before?.[key];
    const b = after?.[key];
    return { key, before: a, after: b, changed: JSON.stringify(a) !== JSON.stringify(b) };
  });
}

function show(value: unknown) {
  if (value === undefined) return <span className="text-muted-foreground">—</span>;
  return <code className="font-mono text-xs break-all">{JSON.stringify(value)}</code>;
}

function ChangeDetails({ log }: { log: AuditLog }) {
  const rows = diffKeys(log.before, log.after);
  return (
    <div className="space-y-3 bg-muted/40 px-4 py-4 text-sm">
      {rows.length ? (
        <table className="w-full max-w-3xl">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="w-40 pb-2 font-medium">Field</th>
              <th className="pb-2 font-medium">Before</th>
              <th className="pb-2 font-medium">After</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className={cn(row.changed && "bg-sunrise-soft/60")}>
                <td className="py-1 pr-3 font-mono text-xs">{row.key}</td>
                <td className="py-1 pr-3">{show(row.before)}</td>
                <td className="py-1">{show(row.after)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-muted-foreground">No field changes recorded.</p>
      )}
      <p className="text-xs text-muted-foreground">
        IP {log.ip_address ?? "—"} · Request {log.request_id ?? "—"} · Entry {log.id}
      </p>
    </div>
  );
}

export function AuditLogViewer() {
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [target, setTarget] = useState("");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);
  const debouncedActor = useDebouncedValue(actor.trim());
  const debouncedTarget = useDebouncedValue(target.trim());

  const filters = {
    action: action || undefined,
    actor_email: debouncedActor || undefined,
    target_id: debouncedTarget || undefined,
  };
  const query = useQuery({
    queryKey: ["admin", "audit-logs", filters, page],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/audit-logs", {
          params: { query: { ...filters, page, page_size: PAGE_SIZE } },
        }),
      ),
    placeholderData: keepPreviousData,
  });

  function exportCsv() {
    downloadCsv(
      `glideup-audit-page-${page}.csv`,
      [
        "created_at",
        "actor_email",
        "action",
        "target_type",
        "target_id",
        "before",
        "after",
        "ip_address",
        "request_id",
      ],
      (query.data?.items ?? []).map((l) => [
        l.created_at,
        l.actor_email ?? "system",
        l.action,
        l.target_type,
        l.target_id,
        JSON.stringify(l.before),
        JSON.stringify(l.after),
        l.ip_address,
        l.request_id,
      ]),
    );
  }

  const onFilter = (setter: (v: string) => void) => (value: string) => {
    setter(value);
    setPage(1);
  };

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Audit log"
        description="Every privileged action: who did what, when, and what changed."
        actions={
          <Button variant="outline" size="sm" onClick={exportCsv} disabled={!query.data?.items.length}>
            <Download /> Export CSV
          </Button>
        }
      />
      <Card>
        <div className="flex flex-col gap-3 border-b p-4 md:flex-row">
          <NativeSelect
            aria-label="Filter by action"
            value={action}
            onChange={(e) => onFilter(setAction)(e.target.value)}
            className="md:w-60"
          >
            {ACTION_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </NativeSelect>
          <Input
            aria-label="Filter by actor email"
            placeholder="Actor email"
            value={actor}
            onChange={(e) => onFilter(setActor)(e.target.value)}
            className="md:max-w-64"
          />
          <Input
            aria-label="Filter by target id"
            placeholder="Target id"
            value={target}
            onChange={(e) => onFilter(setTarget)(e.target.value)}
            className="md:max-w-80"
          />
        </div>

        {query.isError ? (
          <ErrorState error={query.error} onRetry={() => query.refetch()} />
        ) : query.isPending ? (
          <div className="space-y-3 p-4">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : query.data.items.length === 0 ? (
          <EmptyState
            icon={<ScrollText className="size-5" aria-hidden />}
            title="No audit entries"
            body="Admin actions such as role changes and suspensions will appear here."
          />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <span className="sr-only">Details</span>
                  </TableHead>
                  <TableHead>When</TableHead>
                  <TableHead>Actor</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead className="hidden md:table-cell">Target</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data.items.map((log) => {
                  const open = expanded === log.id;
                  return (
                    <Fragment key={log.id}>
                      <TableRow>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-expanded={open}
                            aria-label={open ? "Hide details" : "Show details"}
                            onClick={() => setExpanded(open ? null : log.id)}
                          >
                            {open ? <ChevronDown /> : <ChevronRight />}
                          </Button>
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-muted-foreground">
                          {formatDateTime(log.created_at)}
                        </TableCell>
                        <TableCell>{log.actor_email ?? <Badge variant="muted">system</Badge>}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="font-mono">
                            {log.action}
                          </Badge>
                        </TableCell>
                        <TableCell className="hidden font-mono text-xs text-muted-foreground md:table-cell">
                          {log.target_type}:{log.target_id?.slice(0, 8)}
                        </TableCell>
                      </TableRow>
                      {open && (
                        <TableRow className="hover:bg-transparent">
                          <TableCell colSpan={5} className="p-0">
                            <ChangeDetails log={log} />
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
            <Pagination page={page} pageSize={PAGE_SIZE} total={query.data.total} onPageChange={setPage} />
          </>
        )}
      </Card>
    </div>
  );
}
