"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Pagination } from "@/components/admin/pagination";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge, Label, NativeSelect, Skeleton, Textarea } from "@/components/ui/primitives";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { AdminUserReport } from "@/lib/api/types";
import { formatDateTime } from "@/lib/utils";

const KIND_LABELS: Record<string, string> = {
  broken_job_link: "Broken job link",
  wrong_question: "Wrong question",
  bad_ai_feedback: "Bad AI feedback",
  other: "Other",
};

function ReportRow({ report, canManage }: { report: AdminUserReport; canManage: boolean }) {
  const client = useQueryClient();
  const [reply, setReply] = useState(report.reply ?? "");
  const handle = useMutation({
    mutationFn: (state: "resolved" | "dismissed") =>
      unwrap(
        api.PATCH("/api/v1/admin/reports/{report_id}", {
          params: { path: { report_id: report.id } },
          body: { state, reply: reply.trim() || null },
        }),
      ),
    onSuccess: () => {
      toast.success("Updated");
      void client.invalidateQueries({ queryKey: ["admin", "reports"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <li className="space-y-2 p-4">
      <p className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="muted">{KIND_LABELS[report.kind] ?? report.kind}</Badge>
        <span className="text-muted-foreground">
          {report.user_email ?? "deleted user"} · {formatDateTime(report.created_at)}
        </span>
        {report.page_url && (
          <Link href={report.page_url} className="text-primary hover:underline">
            {report.page_url}
          </Link>
        )}
        {report.state !== "open" && <Badge variant={report.state === "resolved" ? "success" : "outline"}>{report.state}</Badge>}
      </p>
      <p className="whitespace-pre-wrap">{report.message}</p>
      {canManage && report.state === "open" ? (
        <div className="flex flex-wrap items-end gap-2">
          <Textarea
            aria-label="Reply to the user"
            placeholder="Optional reply the user will see"
            className="min-h-16 flex-1"
            value={reply}
            onChange={(e) => setReply(e.target.value)}
          />
          <Button size="sm" onClick={() => handle.mutate("resolved")} disabled={handle.isPending}>
            <Check /> Resolve
          </Button>
          <Button size="sm" variant="outline" onClick={() => handle.mutate("dismissed")} disabled={handle.isPending}>
            <X /> Dismiss
          </Button>
        </div>
      ) : (
        report.reply && <p className="text-sm text-muted-foreground">Reply: {report.reply}</p>
      )}
    </li>
  );
}

export function ReportsAdmin({ canManage }: { canManage: boolean }) {
  const [state, setState] = useState("open");
  const [page, setPage] = useState(1);
  const list = useQuery({
    queryKey: ["admin", "reports", state, page],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/reports", {
          params: { query: { state: (state || undefined) as "open" | undefined, page, page_size: 25 } },
        }),
      ),
    placeholderData: keepPreviousData,
  });
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="User reports"
        description={`Problems users flagged: broken job links, wrong questions, bad AI feedback.${canManage ? "" : " Read-only for your role."}`}
      />
      <Card>
        <div className="flex items-center gap-3 border-b p-4">
          <Label htmlFor="rep-state">Show</Label>
          <NativeSelect
            id="rep-state"
            className="w-40"
            value={state}
            onChange={(e) => {
              setState(e.target.value);
              setPage(1);
            }}
          >
            <option value="open">Open</option>
            <option value="resolved">Resolved</option>
            <option value="dismissed">Dismissed</option>
          </NativeSelect>
        </div>
        {list.isError ? (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        ) : list.isPending ? (
          <Skeleton className="m-4 h-48" />
        ) : list.data.items.length === 0 ? (
          <EmptyState title={state === "open" ? "No open reports" : "Nothing here"} />
        ) : (
          <>
            <ul className="divide-y">
              {list.data.items.map((r) => (
                <ReportRow key={r.id} report={r} canManage={canManage} />
              ))}
            </ul>
            <Pagination page={page} pageSize={25} total={list.data.total} onPageChange={setPage} />
          </>
        )}
      </Card>
    </div>
  );
}
