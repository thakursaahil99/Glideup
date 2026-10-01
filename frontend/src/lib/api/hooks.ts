"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api, unwrap } from "@/lib/api/client";
import type { ParsedResume, Profile, ProfileUpdate, Resume } from "@/lib/api/types";

export const keys = {
  profile: ["me", "profile"] as const,
  activeResume: ["me", "resume", "active"] as const,
  resumes: ["me", "resumes"] as const,
};

const PENDING: Resume["status"][] = ["uploaded", "parsing"];

export function isParsing(resume: Pick<Resume, "status"> | null | undefined) {
  return Boolean(resume && PENDING.includes(resume.status));
}

export function useProfile() {
  return useQuery({
    queryKey: keys.profile,
    queryFn: () => unwrap(api.GET("/api/v1/users/me/profile")),
  });
}

export function useUpdateProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ProfileUpdate) => unwrap(api.PUT("/api/v1/users/me/profile", { body })),
    onSuccess: (profile: Profile) => client.setQueryData(keys.profile, profile),
  });
}

/** The active resume, or null if none. Polls while parsing is in progress. */
export function useActiveResume() {
  return useQuery({
    queryKey: keys.activeResume,
    queryFn: async () => {
      try {
        return await unwrap(api.GET("/api/v1/resumes/active"));
      } catch (error) {
        if (error instanceof ApiError && error.code === "no_resume") return null;
        throw error;
      }
    },
    refetchInterval: (query) => (isParsing(query.state.data) ? 2000 : false),
  });
}

export function useResumes() {
  return useQuery({
    queryKey: keys.resumes,
    queryFn: () => unwrap(api.GET("/api/v1/resumes")),
  });
}

function useInvalidateResumes() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ["me"] });
}

/**
 * Multipart upload through the BFF. Uses fetch directly so the browser sets the
 * multipart boundary; the response is the typed ResumeOut.
 */
export async function uploadResume(file: File): Promise<Resume> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/backend/resumes", { method: "POST", body: form });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      response.status,
      body?.error?.code ?? "upload_failed",
      body?.error?.message ?? "Upload failed",
      body?.error?.request_id,
    );
  }
  return body as Resume;
}

export function useUploadResume() {
  const client = useQueryClient();
  const invalidate = useInvalidateResumes();
  return useMutation({
    mutationFn: uploadResume,
    onSuccess: (resume) => {
      client.setQueryData(keys.activeResume, resume);
      invalidate();
    },
  });
}

export function useSaveParsed(resumeId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (parsed: ParsedResume) =>
      unwrap(
        api.PUT("/api/v1/resumes/{resume_id}/parsed", {
          params: { path: { resume_id: resumeId } },
          body: parsed,
        }),
      ),
    onSuccess: (resume) => client.setQueryData(keys.activeResume, resume),
  });
}

export function useResumeAction(action: "reparse" | "activate" | "delete") {
  const invalidate = useInvalidateResumes();
  return useMutation({
    mutationFn: async (resumeId: string) => {
      const params = { params: { path: { resume_id: resumeId } } };
      if (action === "reparse") await unwrap(api.POST("/api/v1/resumes/{resume_id}/reparse", params));
      else if (action === "activate") await unwrap(api.POST("/api/v1/resumes/{resume_id}/activate", params));
      else await unwrap(api.DELETE("/api/v1/resumes/{resume_id}", params));
    },
    onSuccess: invalidate,
  });
}
