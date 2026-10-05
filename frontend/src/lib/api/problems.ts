"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { Difficulty, Verdict } from "@/lib/api/types";
import { newClientId } from "@/lib/interview-room";

export function isPending(verdict: Verdict | undefined): boolean {
  return verdict === "queued" || verdict === "running";
}

export function useProblems(difficulty: Difficulty | null) {
  return useQuery({
    queryKey: ["problems", difficulty],
    queryFn: () =>
      unwrap(api.GET("/api/v1/problems", { params: { query: { difficulty: difficulty ?? undefined } } })),
  });
}

export function useProblem(slug: string) {
  return useQuery({
    queryKey: ["problem", slug],
    queryFn: () => unwrap(api.GET("/api/v1/problems/{slug}", { params: { path: { slug } } })),
  });
}

export function useRunCode(slug: string) {
  return useMutation({
    mutationFn: (body: { language: string; code: string }) =>
      unwrap(api.POST("/api/v1/problems/{slug}/run", { params: { path: { slug } }, body })),
  });
}

export function useSubmitCode(slug: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { language: string; code: string }) =>
      unwrap(
        api.POST("/api/v1/problems/{slug}/submissions", {
          params: { path: { slug }, header: { "idempotency-key": newClientId() } },
          body,
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: ["submissions", slug] }),
  });
}

export function useSubmission(id: string | null) {
  return useQuery({
    queryKey: ["submission", id],
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(api.GET("/api/v1/submissions/{submission_id}", { params: { path: { submission_id: id! } } })),
    refetchInterval: (query) => (isPending(query.state.data?.verdict) ? 1500 : false),
  });
}

export function useMySubmissions(slug: string) {
  return useQuery({
    queryKey: ["submissions", slug],
    queryFn: () => unwrap(api.GET("/api/v1/problems/{slug}/submissions", { params: { path: { slug } } })),
  });
}
