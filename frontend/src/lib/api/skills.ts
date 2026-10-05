"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";

export function useFrameworks() {
  return useQuery({ queryKey: ["frameworks"], queryFn: () => unwrap(api.GET("/api/v1/frameworks")) });
}

export function useStartAttempt() {
  return useMutation({
    mutationFn: (key: string) =>
      unwrap(api.POST("/api/v1/frameworks/{key}/attempts", { params: { path: { key } } })),
  });
}

export function useAttempt(id: string) {
  return useQuery({
    queryKey: ["attempt", id],
    queryFn: () =>
      unwrap(api.GET("/api/v1/framework-attempts/{attempt_id}", { params: { path: { attempt_id: id } } })),
    refetchInterval: (query) => (query.state.data?.status === "grading" ? 2500 : false),
  });
}

export function useSaveAnswers(id: string) {
  return useMutation({
    mutationFn: (answers: Record<string, number | string | null>) =>
      unwrap(
        api.PUT("/api/v1/framework-attempts/{attempt_id}/answers", {
          params: { path: { attempt_id: id } },
          body: { answers },
        }),
      ),
  });
}

export function useSubmitAttempt(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(api.POST("/api/v1/framework-attempts/{attempt_id}/submit", { params: { path: { attempt_id: id } } })),
    onSuccess: (attempt) => {
      client.setQueryData(["attempt", id], attempt);
      void client.invalidateQueries({ queryKey: ["frameworks"] });
      void client.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useMySkills() {
  return useQuery({ queryKey: ["skills"], queryFn: () => unwrap(api.GET("/api/v1/me/skills")) });
}
