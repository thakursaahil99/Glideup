import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { rubricProblems } from "@/components/admin/interviews-admin";
import { scoreTrend } from "@/components/dashboard/interview-score-card";
import { ReportBody } from "@/components/interviews/interview-report";
import { formatClock, InterviewRoom } from "@/components/interviews/interview-room";
import { statusLabel } from "@/components/interviews/interviews-home";
import type { InterviewDetail, InterviewMessage, InterviewState, InterviewSummary, ReportResult } from "@/lib/api/types";
import { diffLines } from "@/lib/diff";
import { initialRoomState, type RoomState, roomReducer } from "@/lib/interview-room";

const state: InterviewState = {
  id: "i1",
  status: "in_progress",
  type_key: "dsa",
  difficulty: "medium",
  duration_minutes: 45,
  current_index: 0,
  total_questions: 2,
  current_kind: "coding",
  followups_used: 0,
  max_followups: 3,
  hints_used: 0,
  started_at: new Date().toISOString(),
  ends_at: new Date(Date.now() + 30 * 60_000).toISOString(),
  ended_at: null,
  end_reason: null,
  job_title: null,
  company_name: null,
};

function message(seq: number, role: "interviewer" | "candidate", content: string, kind = "question"): InterviewMessage {
  return {
    id: `m${seq}`,
    seq,
    role,
    kind,
    question_index: 0,
    content,
    attachment: null,
    interrupted: false,
    created_at: new Date().toISOString(),
  };
}

const detail: InterviewDetail = {
  interview: state,
  type_name: "DSA / coding",
  messages: [message(1, "interviewer", "Hi!", "intro"), message(2, "interviewer", "Two sum?")],
  report_status: null,
  overall_score: null,
  error: null,
};

describe("roomReducer", () => {
  it("assembles a streamed reply and keeps messages unique and ordered", () => {
    let s: RoomState = roomReducer(initialRoomState(), { type: "state", busy: false, ...detail });
    s = roomReducer(s, { type: "sending" });
    expect(s.busy).toBe(true);
    s = roomReducer(s, { type: "message", message: message(3, "candidate", "Hash map", "answer") });
    s = roomReducer(s, { type: "message", message: message(3, "candidate", "Hash map", "answer") }); // dup
    s = roomReducer(s, { type: "stream_start", id: "x", kind: "followup" });
    s = roomReducer(s, { type: "delta", id: "x", text: "Complex" });
    s = roomReducer(s, { type: "delta", id: "other", text: "ignored" });
    s = roomReducer(s, { type: "delta", id: "x", text: "ity?" });
    expect(s.streaming?.text).toBe("Complexity?");
    s = roomReducer(s, { type: "stream_end", message: message(4, "interviewer", "Complexity?", "followup") });
    expect(s.streaming).toBeNull();
    s = roomReducer(s, { type: "interview", interview: { ...state, followups_used: 1 } });
    expect(s.busy).toBe(false);
    expect(s.messages.map((m) => m.seq)).toEqual([1, 2, 3, 4]);
  });

  it("drops a half-streamed reply when the connection breaks and surfaces errors", () => {
    let s = roomReducer(initialRoomState(detail), { type: "stream_start", id: "x", kind: "hint" });
    s = roomReducer(s, { type: "connection", value: "reconnecting", error: "Connection lost" });
    expect(s.streaming).toBeNull();
    expect(s.error).toBe("Connection lost");
    s = roomReducer(s, { type: "sending" });
    s = roomReducer(s, { type: "error", code: "interview_ended", message: "This interview has ended." });
    expect(s).toMatchObject({ busy: false, error: "This interview has ended." });
  });
});

const room = {
  state: { ...initialRoomState(detail), connection: "open" } as RoomState,
  start: vi.fn(),
  answer: vi.fn(() => true),
  hint: vi.fn(),
  skip: vi.fn(),
  end: vi.fn(),
};
let current: InterviewDetail = detail;

vi.mock("@/lib/interview-room", async (original) => ({
  ...(await original<typeof import("@/lib/interview-room")>()),
  useInterviewRoom: () => room,
}));
vi.mock("@/lib/api/interviews", async (original) => ({
  ...(await original<typeof import("@/lib/api/interviews")>()),
  useInterview: () => ({ data: current, isPending: false, isError: false, refetch: vi.fn() }),
}));

describe("InterviewRoom", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    current = detail;
    room.state = { ...initialRoomState(detail), connection: "open" };
  });

  it("asks for confirmation before starting the clock", () => {
    const ready = { ...state, status: "ready" as const, started_at: null, ends_at: null };
    current = { ...detail, interview: ready, messages: [] };
    room.state = { ...initialRoomState(current), connection: "open" };
    render(<InterviewRoom interviewId="i1" />);
    fireEvent.click(screen.getByRole("button", { name: /Start interview/ }));
    expect(room.start).toHaveBeenCalledOnce();
  });

  it("sends the answer with the code panel for coding questions", () => {
    render(<InterviewRoom interviewId="i1" />);
    expect(screen.getByText("Two sum?")).toBeInTheDocument();
    expect(screen.getByText(/Question 1 of 2/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Code"), { target: { value: "def two_sum(): ..." } });
    fireEvent.change(screen.getByLabelText("Your answer"), { target: { value: "Use a hash map." } });
    fireEvent.click(screen.getByRole("button", { name: /Send/ }));
    expect(room.answer).toHaveBeenCalledWith("Use a hash map.", "def two_sum(): ...");
    fireEvent.click(screen.getByRole("button", { name: /Hint/ }));
    expect(room.hint).toHaveBeenCalledOnce();
  });

  it("confirms before ending and links to the report afterwards", () => {
    const { unmount } = render(<InterviewRoom interviewId="i1" />);
    fireEvent.click(screen.getByRole("button", { name: /^End$/ }));
    fireEvent.click(screen.getByRole("button", { name: "End interview" }));
    expect(room.end).toHaveBeenCalledOnce();
    unmount();

    room.state = { ...room.state, interview: { ...state, status: "completed" } };
    render(<InterviewRoom interviewId="i1" />);
    expect(screen.getByRole("link", { name: /See your report/ })).toHaveAttribute("href", "/interviews/i1/report");
  });
});

const result: ReportResult = {
  overall_score: 64,
  rubric_score: 70,
  questions_score: 55,
  summary: "Solid approach, weak on complexity.",
  criteria: [
    { key: "approach", name: "Approach", weight: 2, score: 4, evidence: "use a hash map", comment: "Good." },
    { key: "complexity", name: "Complexity", weight: 1, score: null, evidence: null, comment: null },
  ],
  questions: [
    { index: 0, prompt: "Two sum?", focus: "Hashing", answered: true, score: 7, feedback: "Nice.", strengths: [], improvements: ["State complexity"] },
    { index: 1, prompt: "Islands?", focus: "Graphs", answered: false, score: 0, feedback: "Not answered.", strengths: [], improvements: [] },
  ],
  strengths: ["Clear"],
  weaknesses: ["Complexity"],
  tips: ["Always state Big-O"],
  next_practice: { type: "dsa", focus: "Graphs", reason: "You skipped it." },
  answered: 1,
  total_questions: 2,
  hints_used: 1,
};

describe("ReportBody", () => {
  it("shows the score, evidence and unanswered questions", () => {
    render(<ReportBody result={result} />);
    expect(screen.getByRole("img", { name: "64% match" })).toBeInTheDocument();
    expect(screen.getByText(/Answered 1 of 2 questions · 1 hint used/)).toBeInTheDocument();
    expect(screen.getByText("use a hash map")).toBeInTheDocument();
    expect(screen.getByText("not judged")).toBeInTheDocument();
    expect(screen.getByText("Not answered")).toBeInTheDocument();
    expect(screen.getByText("State complexity")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Practise again/ })).toHaveAttribute("href", "/interviews");
  });
});

describe("helpers", () => {
  it("formats the countdown", () => {
    expect(formatClock(605)).toBe("10:05");
    expect(formatClock(-3)).toBe("0:00");
  });

  it("labels interview status", () => {
    const base = { status: "completed", report_status: "done" } as InterviewSummary;
    expect(statusLabel(base)).toBe("Report ready");
    expect(statusLabel({ ...base, report_status: "skipped" })).toBe("No answers");
    expect(statusLabel({ ...base, status: "preparing" })).toBe("Preparing");
  });

  it("averages scores and tracks the trend", () => {
    const items = [{ overall_score: 70 }, { overall_score: null }, { overall_score: 60 }] as InterviewSummary[];
    expect(scoreTrend(items)).toEqual({ average: 65, delta: 10 });
    expect(scoreTrend([])).toEqual({ average: null, delta: null });
  });

  it("diffs prompt versions line by line", () => {
    expect(diffLines("a\nb\nc", "a\nc\nd")).toEqual([
      { type: "same", text: "a" },
      { type: "removed", text: "b" },
      { type: "same", text: "c" },
      { type: "added", text: "d" },
    ]);
  });

  it("validates rubrics like the API does", () => {
    const ok = [{ key: "star", name: "STAR", description: "", weight: 1 }];
    expect(rubricProblems(ok)).toBeNull();
    expect(rubricProblems([])).toMatch(/at least one/);
    expect(rubricProblems([...ok, ...ok])).toMatch(/unique/);
    expect(rubricProblems([{ ...ok[0], key: "Bad Key" }])).toMatch(/lower-case/);
  });
});
