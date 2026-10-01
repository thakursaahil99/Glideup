"use client";

import {
  type InfiniteData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { ExperienceLevel, JobDetail, JobSearchResponse, WorkMode } from "@/lib/api/types";

/** Filters live in the URL, so a search can be bookmarked and shared. */
export type RemoteFilter = "india" | "worldwide";
export type Region = "india" | "international";

export type JobFilters = {
  q: string;
  location: string;
  countries: string[];
  states: string[];
  cities: string[];
  remote: RemoteFilter | null;
  region: Region | null;
  modes: WorkMode[];
  levels: ExperienceLevel[];
  skills: string[];
  companies: string[];
  days: number | null;
  sort: "relevance" | "newest";
};

export const EMPTY_FILTERS: JobFilters = {
  q: "",
  location: "",
  countries: [],
  states: [],
  cities: [],
  remote: null,
  region: null,
  modes: [],
  levels: [],
  skills: [],
  companies: [],
  days: null,
  sort: "relevance",
};

function oneOf<T extends string>(value: string | null, allowed: readonly T[]): T | null {
  return allowed.includes(value as T) ? (value as T) : null;
}

export function filtersFromParams(params: URLSearchParams): JobFilters {
  const days = Number(params.get("days"));
  return {
    q: params.get("q") ?? "",
    location: params.get("location") ?? "",
    countries: params.getAll("country").filter((c) => /^[A-Z]{2}$/.test(c)),
    states: params.getAll("state"),
    cities: params.getAll("city"),
    remote: oneOf(params.get("remote"), ["india", "worldwide"] as const),
    region: oneOf(params.get("region"), ["india", "international"] as const),
    modes: params.getAll("mode") as WorkMode[],
    levels: params.getAll("level") as ExperienceLevel[],
    skills: params.getAll("skill"),
    companies: params.getAll("company"),
    days: Number.isFinite(days) && days > 0 ? days : null,
    sort: params.get("sort") === "newest" ? "newest" : "relevance",
  };
}

export function filtersToParams(filters: JobFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.location) params.set("location", filters.location);
  filters.countries.forEach((c) => params.append("country", c));
  filters.states.forEach((s) => params.append("state", s));
  filters.cities.forEach((c) => params.append("city", c));
  if (filters.remote) params.set("remote", filters.remote);
  if (filters.region) params.set("region", filters.region);
  filters.modes.forEach((m) => params.append("mode", m));
  filters.levels.forEach((l) => params.append("level", l));
  filters.skills.forEach((s) => params.append("skill", s));
  filters.companies.forEach((c) => params.append("company", c));
  if (filters.days) params.set("days", String(filters.days));
  if (filters.sort !== "relevance") params.set("sort", filters.sort);
  return params;
}

export function activeFilterCount(filters: JobFilters): number {
  return (
    Number(Boolean(filters.location)) +
    filters.countries.length +
    filters.states.length +
    filters.cities.length +
    Number(Boolean(filters.remote)) +
    Number(Boolean(filters.region)) +
    filters.modes.length +
    filters.levels.length +
    filters.skills.length +
    filters.companies.length +
    Number(Boolean(filters.days))
  );
}

const jobKeys = {
  search: (filters: JobFilters) => ["jobs", "search", filters] as const,
  detail: (id: string) => ["jobs", "detail", id] as const,
  saved: ["jobs", "saved"] as const,
};

export function useJobSearch(filters: JobFilters) {
  return useInfiniteQuery({
    queryKey: jobKeys.search(filters),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/jobs", {
          params: {
            query: {
              q: filters.q || undefined,
              location: filters.location || undefined,
              country: filters.countries.length ? filters.countries : undefined,
              state: filters.states.length ? filters.states : undefined,
              city: filters.cities.length ? filters.cities : undefined,
              remote: filters.remote ?? undefined,
              region: filters.region ?? undefined,
              work_mode: filters.modes.length ? filters.modes : undefined,
              experience: filters.levels.length ? filters.levels : undefined,
              skills: filters.skills.length ? filters.skills : undefined,
              company: filters.companies.length ? filters.companies : undefined,
              posted_within_days: filters.days ?? undefined,
              sort: filters.sort,
              cursor: pageParam ?? undefined,
            },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: (previous) => previous,
  });
}

export function useJob(id: string) {
  return useQuery({
    queryKey: jobKeys.detail(id),
    queryFn: () => unwrap(api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: id } } })),
  });
}

export function useSavedJobs() {
  return useQuery({
    queryKey: jobKeys.saved,
    queryFn: () => unwrap(api.GET("/api/v1/jobs/saved")),
  });
}

/** Save / unsave with an optimistic update across every cached list that shows the job. */
export function useToggleSave() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, saved }: { id: string; saved: boolean }) => {
      const params = { params: { path: { job_id: id } } };
      if (saved) await unwrap(api.PUT("/api/v1/jobs/{job_id}/save", params));
      else await unwrap(api.DELETE("/api/v1/jobs/{job_id}/save", params));
    },
    onMutate: async ({ id, saved }) => {
      await client.cancelQueries({ queryKey: ["jobs"] });
      const searches = client.getQueriesData<InfiniteData<JobSearchResponse>>({
        queryKey: ["jobs", "search"],
      });
      for (const [key, data] of searches) {
        if (!data) continue;
        client.setQueryData(key, {
          ...data,
          pages: data.pages.map((page) => ({
            ...page,
            items: page.items.map((job) => (job.id === id ? { ...job, is_saved: saved } : job)),
          })),
        });
      }
      client.setQueryData<JobDetail>(jobKeys.detail(id), (job) => (job ? { ...job, is_saved: saved } : job));
      return { searches };
    },
    onError: (_error, _vars, context) => {
      for (const [key, data] of context?.searches ?? []) client.setQueryData(key, data);
    },
    onSettled: () => client.invalidateQueries({ queryKey: jobKeys.saved }),
  });
}
