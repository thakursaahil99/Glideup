"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { Difficulty } from "@/lib/api/types";

export const interviewKeys = {
  types: ["interviews", "types"] as const,
  list: ["interviews", "list"] as const,
  detail: (id: string) => ["interviews", "detail", id] as const,
  report: (id: string) => ["interviews", "report", id] as const,
};

export function useInterviewTypes() {
  return useQuery({
    queryKey: interviewKeys.types,
    queryFn: () => unwrap(api.GET("/api/v1/interviews/types")),
    staleTime: 5 * 60_000,
  });
}

export function useInterviews() {
  return useQuery({
    queryKey: interviewKeys.list,
    queryFn: () => unwrap(api.GET("/api/v1/interviews")),
  });
}

export function useInterview(id: string) {
  return useQuery({
    queryKey: interviewKeys.detail(id),
    queryFn: () =>
      unwrap(api.GET("/api/v1/interviews/{interview_id}", { params: { path: { interview_id: id } } })),
    // Job-specific interviews write their questions in the background.
    refetchInterval: (query) => (query.state.data?.interview.status === "preparing" ? 2000 : false),
  });
}

export function useCreateInterview() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { type_key: string; difficulty?: Difficulty; job_id?: string }) =>
      unwrap(api.POST("/api/v1/interviews", { body })),
    onSuccess: (detail) => {
      client.setQueryData(interviewKeys.detail(detail.interview.id), detail);
      void client.invalidateQueries({ queryKey: interviewKeys.list });
    },
  });
}

export function isReportWorking(status: string | undefined | null): boolean {
  return status === "pending" || status === "generating";
}

export function useReport(id: string) {
  return useQuery({
    queryKey: interviewKeys.report(id),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/interviews/{interview_id}/report", { params: { path: { interview_id: id } } }),
      ),
    refetchInterval: (query) => (isReportWorking(query.state.data?.status) ? 3000 : false),
  });
}

export function useRetryReport(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/interviews/{interview_id}/report/retry", {
          params: { path: { interview_id: id } },
        }),
      ),
    onSuccess: (report) => client.setQueryData(interviewKeys.report(id), report),
  });
}

export async function fetchTicket(id: string) {
  return unwrap(
    api.POST("/api/v1/interviews/{interview_id}/ticket", { params: { path: { interview_id: id } } }),
  );
}
