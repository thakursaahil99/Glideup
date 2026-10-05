"use client";

import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";

/** Optional features for the signed-in user. Unknown while loading = treat as on. */
export function useFlags() {
  return useQuery({
    queryKey: ["flags"],
    queryFn: () => unwrap(api.GET("/api/v1/me/flags")),
    staleTime: 60_000,
  });
}

export function useFlag(key: string): boolean {
  const { data } = useFlags();
  return data?.[key] ?? true;
}

export function useAnnouncements() {
  return useQuery({
    queryKey: ["announcements"],
    queryFn: () => unwrap(api.GET("/api/v1/announcements")),
    staleTime: 5 * 60_000,
  });
}
