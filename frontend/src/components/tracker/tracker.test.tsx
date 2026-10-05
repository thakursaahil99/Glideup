import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardInsights } from "@/components/dashboard/dashboard-insights";
import { ReportProblem } from "@/components/report-problem";
import { TrackButton } from "@/components/tracker/track-button";
import { groupByStatus, TrackerBoard } from "@/components/tracker/tracker-board";
import type { Application, DashboardData } from "@/lib/api/types";
import { speechInputSupported } from "@/lib/speech";

const now = new Date().toISOString();
const app = (id: string, status: Application["status"], position: number, jobId: string | null = null): Application => ({
  id,
  job_id: jobId,
  company: `Co ${id}`,
  title: `Role ${id}`,
  url: null,
  location: null,
  status,
  position,
  applied_at: null,
  salary: null,
  notes: null,
  created_at: now,
  updated_at: now,
  events: [{ kind: "created", from_status: null, to_status: status, note: null, created_at: now }],
});

const apps = [app("a", "applied", 1), app("b", "applied", 0), app("c", "saved", 0, "job-1")];
const updateApp = vi.fn();
const createApp = vi.fn();
const report = vi.fn();

const dashboard: DashboardData = {
  applications: { saved: 1, applied: 2, screening: 0, interviewing: 1, offer: 0, rejected: 0, withdrawn: 0 },
  interview_trend: [],
  skills: [],
  weak_topics: [{ topic: "Result", source: "interviews", score: 40 }],
  streak_days: 3,
  active_today: true,
  reminders: [],
  totals: { applications: 4, interviews: 1, problems_solved: 5, tests: 1 },
  next_step: { title: "Do a mock interview", body: "Practise.", href: "/interviews" },
  activity: [],
};

vi.mock("next/navigation", () => ({ usePathname: () => "/jobs/job-1" }));
vi.mock("@/lib/api/tracker", () => ({
  useApplications: () => ({ data: apps, isPending: false, isError: false }),
  useCreateApplication: () => ({ mutate: createApp, isPending: false }),
  useUpdateApplication: () => ({ mutate: updateApp, isPending: false }),
  useDeleteApplication: () => ({ mutate: vi.fn(), isPending: false }),
  useReminders: () => ({ data: [] }),
  useCreateReminder: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateReminder: () => ({ mutate: vi.fn(), isPending: false }),
  useDashboard: () => ({ data: dashboard, isPending: false }),
  useReportProblem: () => ({ mutate: report, isPending: false }),
}));
vi.mock("@/lib/api/interviews", () => ({ useInterviews: () => ({ data: [] }) }));

beforeEach(() => vi.clearAllMocks());

describe("tracker", () => {
  it("groups cards into ordered columns", () => {
    const columns = groupByStatus(apps);
    expect(columns.applied.map((a) => a.id)).toEqual(["b", "a"]);
    expect(columns.saved.map((a) => a.id)).toEqual(["c"]);
    expect(columns.offer).toEqual([]);
  });

  it("renders the board and moves a card with the keyboard-friendly menu", () => {
    render(<TrackerBoard />);
    const applied = screen.getByRole("region", { name: "Applied" });
    expect(within(applied).getAllByRole("listitem")).toHaveLength(2);
    fireEvent.change(screen.getByLabelText("Move Role a at Co a"), { target: { value: "interviewing" } });
    expect(updateApp).toHaveBeenCalledWith({ id: "a", status: "interviewing" }, expect.any(Object));
  });

  it("shows whether a job is already tracked", () => {
    const { unmount } = render(<TrackButton jobId="job-1" />);
    expect(screen.getByRole("link", { name: /Tracked · saved/ })).toHaveAttribute("href", "/tracker");
    unmount();
    render(<TrackButton jobId="job-2" />);
    fireEvent.click(screen.getByRole("button", { name: /Track/ }));
    expect(createApp).toHaveBeenCalledWith({ job_id: "job-2", status: "saved" }, expect.any(Object));
  });
});

describe("dashboard", () => {
  it("shows the next step, streak and weak topics", () => {
    render(<DashboardInsights />);
    expect(screen.getByText("Do a mock interview")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Go/ })).toHaveAttribute("href", "/interviews");
    expect(screen.getByText("3 days")).toBeInTheDocument();
    expect(screen.getByText("Result")).toBeInTheDocument();
    expect(screen.getByText(/Finish two interviews/)).toBeInTheDocument();
  });
});

describe("report a problem", () => {
  it("sends the report with the page it came from", () => {
    render(<ReportProblem kind="broken_job_link" targetType="job" targetId="job-1" />);
    fireEvent.click(screen.getByRole("button", { name: /Report a problem/ }));
    fireEvent.change(screen.getByLabelText("Details"), { target: { value: "The link is dead" } });
    fireEvent.click(screen.getByRole("button", { name: "Send report" }));
    expect(report).toHaveBeenCalledWith(
      { kind: "broken_job_link", message: "The link is dead", target_type: "job", target_id: "job-1", page_url: "/jobs/job-1" },
      expect.any(Object),
    );
  });

  it("detects voice support", () => {
    expect(speechInputSupported()).toBe(false); // jsdom has no SpeechRecognition
  });
});
