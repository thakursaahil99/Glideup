import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { JobCard, postedAgo } from "@/components/jobs/job-card";
import { JobFiltersPanel } from "@/components/jobs/job-filters";
import {
  activeFilterCount,
  EMPTY_FILTERS,
  filtersFromParams,
  filtersToParams,
  type JobFilters,
} from "@/lib/api/jobs";
import type { JobCard as Job } from "@/lib/api/types";

const mutate = vi.fn();
vi.mock("@/lib/api/jobs", async (original) => ({
  ...(await original<typeof import("@/lib/api/jobs")>()),
  useToggleSave: () => ({ mutate, isPending: false }),
}));

const job: Job = {
  id: "j1",
  title: "Senior Backend Engineer",
  company_name: "Groww",
  location: "Bengaluru, India",
  country: "IN",
  countries: ["IN"],
  states: ["Karnataka"],
  cities: ["Bengaluru"],
  remote_scope: null,
  work_mode: "hybrid",
  experience_level: "senior",
  employment_type: "Full-time",
  skills: ["Python", "Kafka", "PostgreSQL", "AWS", "Docker", "Kubernetes"],
  posted_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
  first_seen_at: new Date().toISOString(),
  salary: "INR 2,000,000–3,000,000/year",
  is_featured: true,
  is_saved: false,
  source: "greenhouse",
  attribution: null,
};

describe("filters <-> URL", () => {
  it("round-trips every filter through the query string", () => {
    const filters: JobFilters = {
      q: "python",
      location: "Bengaluru",
      countries: ["IN"],
      states: ["Karnataka"],
      cities: ["Bengaluru"],
      remote: "india",
      region: "india",
      modes: ["remote", "hybrid"],
      levels: ["senior"],
      skills: ["Python", "Kafka"],
      companies: ["Groww"],
      days: 7,
      sort: "newest",
    };
    const params = filtersToParams(filters);
    expect(params.toString()).toContain("mode=remote&mode=hybrid");
    expect(filtersFromParams(params)).toEqual(filters);
    expect(activeFilterCount(filters)).toBe(13);
  });

  it("ignores junk and defaults safely", () => {
    const filters = filtersFromParams(
      new URLSearchParams("days=abc&sort=evil&country=india&remote=mars&region=europe"),
    );
    expect(filters).toEqual(EMPTY_FILTERS);
    expect(filtersToParams(EMPTY_FILTERS).toString()).toBe("");
  });
});

describe("JobCard", () => {
  it("shows the essentials and links to the detail page", () => {
    render(<JobCard job={job} />);
    expect(screen.getByRole("link", { name: job.title })).toHaveAttribute("href", "/jobs/j1");
    expect(screen.getByText("Hybrid")).toBeInTheDocument();
    expect(screen.getByText("Senior")).toBeInTheDocument();
    expect(screen.getByText("Featured")).toBeInTheDocument();
    expect(screen.getByText(/Posted 3 days ago/)).toBeInTheDocument();
    expect(screen.queryByText("Kubernetes")).not.toBeInTheDocument(); // only the first five skills
  });

  it("saves with one click", () => {
    render(<JobCard job={job} />);
    fireEvent.click(screen.getByRole("button", { name: `Save ${job.title}` }));
    expect(mutate).toHaveBeenCalledWith({ id: "j1", saved: true }, expect.any(Object));
  });

  it("formats posting age", () => {
    expect(postedAgo(new Date().toISOString())).toBe("today");
    expect(postedAgo(new Date(Date.now() - 65 * 86_400_000).toISOString())).toBe("2 months ago");
    expect(postedAgo(null)).toBeNull();
  });
});

describe("JobFiltersPanel", () => {
  it("toggles chips with live facet counts and clears everything", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <JobFiltersPanel
        filters={EMPTY_FILTERS}
        facets={{ work_mode: { remote: 120 }, skills: { Python: 40 }, company: { Groww: 7 } }}
        onChange={onChange}
      />,
    );
    const remote = screen.getByRole("button", { name: /Remote/ });
    expect(remote).toHaveTextContent("120");
    fireEvent.click(remote);
    expect(onChange).toHaveBeenLastCalledWith({ ...EMPTY_FILTERS, modes: ["remote"] });
    fireEvent.click(screen.getByRole("button", { name: /Python/ }));
    expect(onChange).toHaveBeenLastCalledWith({ ...EMPTY_FILTERS, skills: ["Python"] });

    rerender(
      <JobFiltersPanel
        filters={{ ...EMPTY_FILTERS, q: "go", modes: ["remote"] }}
        facets={{}}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Clear/ }));
    expect(onChange).toHaveBeenLastCalledWith({ ...EMPTY_FILTERS, q: "go" }); // keeps the keyword
  });
});
