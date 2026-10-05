"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { Application, ApplicationStatus } from "@/lib/api/types";

const APPS = ["applications"];
const REMINDERS = ["reminders"];

export function useApplications() {
  return useQuery({ queryKey: APPS, queryFn: () => unwrap(api.GET("/api/v1/applications")) });
}

export function useCreateApplication() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      job_id?: string;
      company?: string;
      title?: string;
      url?: string;
      location?: string;
      status?: ApplicationStatus;
      notes?: string;
    }) => unwrap(api.POST("/api/v1/applications", { body: { ...body, status: body.status ?? "saved" } })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: APPS });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

/** Optimistic move/edit: the card jumps immediately, and rolls back on error. */
export function useUpdateApplication() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: string;
      status?: ApplicationStatus;
      position?: number;
      notes?: string;
      salary?: string;
      note?: string;
    }) => unwrap(api.PATCH("/api/v1/applications/{application_id}", { params: { path: { application_id: id } }, body })),
    onMutate: async ({ id, status, position }) => {
      await client.cancelQueries({ queryKey: APPS });
      const previous = client.getQueryData<Application[]>(APPS);
      if (previous && status) {
        client.setQueryData<Application[]>(
          APPS,
          previous.map((a) => (a.id === id ? { ...a, status, position: position ?? -1 } : a)),
        );
      }
      return { previous };
    },
    onError: (_e, _vars, context) => client.setQueryData(APPS, context?.previous),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: APPS });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useDeleteApplication() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/v1/applications/{application_id}", { params: { path: { application_id: id } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: APPS }),
  });
}

export function useReminders() {
  return useQuery({ queryKey: REMINDERS, queryFn: () => unwrap(api.GET("/api/v1/reminders")) });
}

export function useCreateReminder() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { title: string; due_at: string; application_id?: string | null }) =>
      unwrap(api.POST("/api/v1/reminders", { body })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: REMINDERS });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useUpdateReminder() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; done?: boolean; due_at?: string }) =>
      unwrap(api.PATCH("/api/v1/reminders/{reminder_id}", { params: { path: { reminder_id: id } }, body })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: REMINDERS });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useDashboard() {
  return useQuery({ queryKey: ["dashboard"], queryFn: () => unwrap(api.GET("/api/v1/dashboard")) });
}

export function useReportProblem() {
  return useMutation({
    mutationFn: (body: {
      kind: "wrong_question" | "bad_ai_feedback" | "broken_job_link" | "other";
      message: string;
      target_type?: string;
      target_id?: string;
      page_url?: string;
    }) => unwrap(api.POST("/api/v1/reports", { body })),
  });
}
