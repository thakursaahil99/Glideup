"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { MatchDetail } from "@/lib/api/types";

export type RecommendationFilters = { india: boolean; remote: boolean };

const matchKeys = {
  detail: (jobId: string) => ["matches", "job", jobId] as const,
  recommended: (filters: RecommendationFilters) => ["matches", "recommended", filters] as const,
};

/** Keep polling while something is still being computed in the background. */
export function isMatchWorking(match: MatchDetail | undefined): boolean {
  const status = match?.analysis?.status;
  return Boolean(match?.embedding_pending || status === "pending" || status === "analyzing");
}

export function useJobMatch(jobId: string) {
  return useQuery({
    queryKey: matchKeys.detail(jobId),
    queryFn: () =>
      unwrap(api.GET("/api/v1/jobs/{job_id}/match", { params: { path: { job_id: jobId } } })),
    refetchInterval: (query) => (isMatchWorking(query.state.data) ? 3000 : false),
  });
}

export function useStartAnalysis(jobId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/jobs/{job_id}/match/analysis", { params: { path: { job_id: jobId } } }),
      ),
    onSuccess: (detail) => client.setQueryData(matchKeys.detail(jobId), detail),
  });
}

export function useRecommendations(filters: RecommendationFilters, pageSize = 20) {
  return useInfiniteQuery({
    queryKey: [...matchKeys.recommended(filters), pageSize],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/matches/recommended", {
          params: {
            query: {
              country: filters.india ? ["IN"] : undefined,
              remote: filters.remote || undefined,
              limit: pageSize,
              cursor: pageParam ?? undefined,
            },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor,
    // The resume may still be embedding; refresh until scores are complete.
    refetchInterval: (query) => (query.state.data?.pages[0]?.embedding_pending ? 5000 : false),
  });
}
