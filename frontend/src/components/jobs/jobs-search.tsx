"use client";

import { Bookmark, Flame, Loader2, Search, SlidersHorizontal, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { JobCard } from "@/components/jobs/job-card";
import { JobFiltersPanel } from "@/components/jobs/job-filters";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input, NativeSelect, Skeleton } from "@/components/ui/primitives";
import {
  activeFilterCount,
  filtersFromParams,
  filtersToParams,
  type JobFilters,
  useJobSearch,
} from "@/lib/api/jobs";

const number = new Intl.NumberFormat("en");

/** Companies with the most openings for the current search; a click narrows to that company. */
export function TopHiringCompanies({
  counts,
  onPick,
  limit = 8,
}: {
  counts: Record<string, number> | undefined;
  onPick: (company: string) => void;
  limit?: number;
}) {
  const top = Object.entries(counts ?? {})
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit);
  if (top.length < 2) return null;
  return (
    <section aria-labelledby="top-hiring-heading" className="mb-4">
      <h3 id="top-hiring-heading" className="mb-2 flex items-center gap-1.5 text-sm font-medium">
        <Flame className="size-4 text-sunrise" aria-hidden /> Hiring the most for this search
      </h3>
      <ul className="flex flex-wrap gap-2">
        {top.map(([company, count]) => (
          <li key={company}>
            <button
              type="button"
              onClick={() => onPick(company)}
              className="rounded-full border bg-card px-3 py-1 text-sm transition-colors hover:border-primary/50 hover:bg-accent"
            >
              {company} <span className="text-muted-foreground">· {number.format(count)}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function JobsSearch() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const filters = filtersFromParams(new URLSearchParams(params.toString()));
  const [draft, setDraft] = useState(filters.q);
  const [mobileFilters, setMobileFilters] = useState(false);
  const query = useJobSearch(filters);
  const sentinel = useRef<HTMLDivElement>(null);

  function apply(next: JobFilters) {
    const qs = filtersToParams(next).toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  // Infinite scroll, with the "Load more" button as the keyboard/screen-reader path.
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = query;
  useEffect(() => {
    const node = sentinel.current;
    if (!node || !hasNextPage) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && !isFetchingNextPage) fetchNextPage();
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const first = query.data?.pages[0];
  const jobs = query.data?.pages.flatMap((p) => p.items) ?? [];
  const filterCount = activeFilterCount(filters);
  const panel = <JobFiltersPanel filters={filters} facets={first?.facets} onChange={apply} />;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Jobs"
        description="Real openings from companies' own job boards, refreshed every few hours."
        actions={
          <>
            <Button asChild variant="sunrise" size="sm">
              <Link href="/jobs/recommended">
                <Sparkles /> Recommended for you
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/jobs/saved">
                <Bookmark /> Saved jobs
              </Link>
            </Button>
          </>
        }
      />

      <form
        role="search"
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          apply({ ...filters, q: draft.trim() });
        }}
      >
        <div className="relative flex-1">
          <Search
            aria-hidden
            className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            type="search"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Job title, skill or company"
            aria-label="Search jobs"
            className="h-11 pl-9"
          />
        </div>
        <Button type="submit" size="lg" className="h-11">
          Search
        </Button>
        <Button
          type="button"
          variant="outline"
          size="lg"
          className="h-11 lg:hidden"
          onClick={() => setMobileFilters(true)}
          aria-label="Filters"
        >
          <SlidersHorizontal /> {filterCount > 0 && filterCount}
        </Button>
      </form>

      <div className="mt-6 grid gap-6 lg:grid-cols-[17rem_1fr]">
        <aside className="hidden lg:block">
          <Card className="sticky top-20 p-5">{panel}</Card>
        </aside>

        <section aria-labelledby="results-heading" className="min-w-0">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 id="results-heading" className="text-sm text-muted-foreground" aria-live="polite">
              {first ? `${number.format(first.total)}${first.total >= 5000 ? "+" : ""} jobs` : "Searching…"}
              {first?.search_backend === "database" && (
                <span className="ml-2 text-warning">· simplified search (search service unavailable)</span>
              )}
            </h2>
            <NativeSelect
              aria-label="Sort"
              value={filters.sort}
              onChange={(e) => apply({ ...filters, sort: e.target.value as JobFilters["sort"] })}
              className="w-40"
            >
              <option value="relevance">Most relevant</option>
              <option value="newest">Newest</option>
              <option value="hiring">Most hiring</option>
            </NativeSelect>
          </div>

          {query.isError ? (
            <Card>
              <ErrorState error={query.error} onRetry={() => query.refetch()} />
            </Card>
          ) : query.isPending ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }, (_, i) => (
                <Skeleton key={i} className="h-36 w-full rounded-xl" />
              ))}
            </div>
          ) : jobs.length === 0 ? (
            <Card>
              <EmptyState
                title="No jobs match these filters"
                body="Try fewer filters, a broader location, or a different keyword."
              />
            </Card>
          ) : (
            <>
              {filters.companies.length === 0 && (
                <TopHiringCompanies
                  counts={first?.facets.company}
                  onPick={(company) => apply({ ...filters, companies: [company] })}
                />
              )}
              <ul className="space-y-3" aria-busy={query.isFetching}>
                {jobs.map((job) => (
                  <li key={job.id}>
                    <JobCard job={job} />
                  </li>
                ))}
              </ul>
              <div ref={sentinel} className="mt-6 flex justify-center">
                {query.hasNextPage ? (
                  <Button
                    variant="outline"
                    onClick={() => query.fetchNextPage()}
                    disabled={query.isFetchingNextPage}
                  >
                    {query.isFetchingNextPage ? <Loader2 className="animate-spin" /> : null}
                    Load more
                  </Button>
                ) : (
                  <p className="text-sm text-muted-foreground">That&apos;s everything for this search.</p>
                )}
              </div>
            </>
          )}
        </section>
      </div>

      <Dialog open={mobileFilters} onOpenChange={setMobileFilters}>
        <DialogContent className="max-h-[85dvh] overflow-y-auto">
          <DialogTitle className="sr-only">Filters</DialogTitle>
          {panel}
          <Button onClick={() => setMobileFilters(false)}>Show results</Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
