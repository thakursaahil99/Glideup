import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MatchBadge, matchTone, ScoreRing } from "@/components/matching/match-badge";
import { MatchCard, PrepareCard, SkillGapCoach } from "@/components/matching/match-panel";
import { isMatchWorking } from "@/lib/api/matches";
import type { MatchAnalysis, MatchDetail } from "@/lib/api/types";

const mutate = vi.fn();
let current: MatchDetail | undefined;

vi.mock("@/lib/api/matches", async (original) => ({
  ...(await original<typeof import("@/lib/api/matches")>()),
  useJobMatch: () => ({ data: current, isPending: false, isError: false, error: null, refetch: vi.fn() }),
  useStartAnalysis: () => ({ mutate, isPending: false }),
}));

const detail: MatchDetail = {
  available: true,
  summary: { score: 82, label: "Strong match", partial: false, matched_skills: 3, total_skills: 5 },
  parts: { semantic: 80, skills: 70, level: 100 },
  matched: [
    { name: "Python", sources: ["resume", "github"] },
    { name: "FastAPI", sources: ["resume"] },
    { name: "PostgreSQL", sources: ["resume"] },
  ],
  transferable: [{ skill: "MySQL", via: "PostgreSQL" }],
  missing: ["Terraform"],
  level: { job_level: "senior", your_years: 7 },
  practice: { languages: ["Python"], frameworks: ["FastAPI"] },
  embedding_pending: false,
  analysis: null,
  analyses_per_day: 30,
};

const done: MatchAnalysis = {
  status: "done",
  stale: false,
  result: {
    summary: "Close fit; Terraform is the gap.",
    strengths: ["Python APIs"],
    missing: [
      {
        skill: "Terraform",
        importance: "required",
        reason: "Infra is managed as code.",
        suggestion: "Build a small AWS stack with Terraform.",
      },
    ],
    weak: [],
  },
  error: null,
  requested_at: new Date().toISOString(),
  analyzed_at: new Date().toISOString(),
  analyzed_by: "mock:mock-1",
};

beforeEach(() => {
  current = detail;
  mutate.mockClear();
});

describe("match badge and ring", () => {
  it("shows the score with a tone per band", () => {
    render(<MatchBadge match={detail.summary!} />);
    expect(screen.getByText("82% match")).toBeInTheDocument();
    expect([90, 60, 40, 10].map(matchTone)).toEqual(["success", "default", "sunrise", "muted"]);
  });

  it("marks partial scores", () => {
    render(<MatchBadge match={{ ...detail.summary!, partial: true }} />);
    expect(screen.getByText("82% match*")).toHaveAttribute(
      "title",
      expect.stringContaining("based on skills only"),
    );
  });

  it("labels the ring for screen readers", () => {
    render(<ScoreRing score={64} />);
    expect(screen.getByRole("img", { name: "64% match" })).toBeInTheDocument();
  });
});

describe("MatchCard", () => {
  it("explains the score with matched, related and missing skills", () => {
    render(<MatchCard jobId="j1" />);
    expect(screen.getByText("Strong match")).toBeInTheDocument();
    expect(screen.getByText("Python")).toHaveAttribute("title", "From your resume and GitHub");
    expect(screen.getByText("MySQL ← PostgreSQL")).toBeInTheDocument();
    expect(screen.getByText("Terraform")).toBeInTheDocument();
    expect(screen.getByText("70%")).toBeInTheDocument();
  });

  it("asks for a resume when we know nothing yet", () => {
    current = { ...detail, available: false, summary: null, parts: null, matched: [], missing: [] };
    render(<MatchCard jobId="j1" />);
    expect(screen.getByRole("link", { name: /Upload resume/ })).toHaveAttribute("href", "/onboarding");
  });
});

describe("SkillGapCoach", () => {
  it("starts an analysis on request", () => {
    render(<SkillGapCoach jobId="j1" />);
    fireEvent.click(screen.getByRole("button", { name: /Analyze my gaps/ }));
    expect(mutate).toHaveBeenCalledOnce();
  });

  it("shows progress while the AI works", () => {
    current = { ...detail, analysis: { ...done, status: "analyzing", result: null, analyzed_at: null } };
    render(<SkillGapCoach jobId="j1" />);
    expect(screen.getByRole("status")).toHaveTextContent(/Reading the job/);
  });

  it("renders gaps with a concrete next step, and offers a refresh when stale", () => {
    current = { ...detail, analysis: { ...done, stale: true } };
    render(<SkillGapCoach jobId="j1" />);
    expect(screen.getByText("Close fit; Terraform is the gap.")).toBeInTheDocument();
    expect(screen.getByText("Required")).toBeInTheDocument();
    expect(screen.getByText("Build a small AWS stack with Terraform.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    expect(mutate).toHaveBeenCalledOnce();
  });

  it("lets the user retry a failed analysis", () => {
    current = { ...detail, analysis: { ...done, status: "failed", result: null, error: "AI unavailable" } };
    render(<SkillGapCoach jobId="j1" />);
    expect(screen.getByRole("alert")).toHaveTextContent("AI unavailable");
    fireEvent.click(screen.getByRole("button", { name: /Try again/ }));
    expect(mutate).toHaveBeenCalledOnce();
  });
});

describe("PrepareCard", () => {
  it("shows the stack a skill test would pre-select", () => {
    render(<PrepareCard jobId="j1" />);
    expect(screen.getByText("Python, FastAPI")).toBeInTheDocument();
  });
});

describe("isMatchWorking", () => {
  it("polls only while something is computing", () => {
    expect(isMatchWorking(detail)).toBe(false);
    expect(isMatchWorking({ ...detail, embedding_pending: true })).toBe(true);
    expect(isMatchWorking({ ...detail, analysis: { ...done, status: "pending" } })).toBe(true);
    expect(isMatchWorking(undefined)).toBe(false);
  });
});
