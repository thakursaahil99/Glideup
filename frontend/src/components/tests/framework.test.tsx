import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SkillsCard } from "@/components/profile/skills-card";
import { answeredCount, AttemptView } from "@/components/tests/attempt-view";
import type { AttemptQuestion, FrameworkAttempt } from "@/lib/api/types";

const questions: AttemptQuestion[] = [
  { id: "q1", type: "mcq", title: "Hooks", statement: "Which hook stores state?", content: { options: ["useRef", "useState"] } },
  { id: "q2", type: "viva", title: "Rendering", statement: "When does a component re-render?", content: {} },
];

const base: FrameworkAttempt = {
  id: "a1",
  framework_key: "react",
  framework_name: "React",
  status: "in_progress",
  ends_at: new Date(Date.now() + 30 * 60_000).toISOString(),
  answers: {},
  questions,
  score: null,
  level: null,
  sections: {},
  error: null,
};

let attempt: FrameworkAttempt = base;
const save = vi.fn();
const submit = vi.fn();

vi.mock("@/lib/api/skills", async (original) => ({
  ...(await original<typeof import("@/lib/api/skills")>()),
  useAttempt: () => ({ data: attempt, isPending: false, isError: false }),
  useSaveAnswers: () => ({ mutate: save, isPending: false }),
  useSubmitAttempt: () => ({ mutate: submit, isPending: false }),
  useMySkills: () => ({
    isPending: false,
    data: {
      skills: [{ skill: "react", kind: "framework", score: 72, level: "advanced", updated_at: new Date().toISOString() }],
      badges: [{ key: "react-practitioner", name: "React practitioner", description: "60+", awarded_at: new Date().toISOString() }],
    },
  }),
}));

beforeEach(() => {
  attempt = base;
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("framework test", () => {
  it("counts answered questions", () => {
    expect(answeredCount(questions, { q1: 0, q2: "   " })).toBe(1);
    expect(answeredCount(questions, { q1: 1, q2: "When state changes" })).toBe(2);
  });

  it("autosaves answers and confirms before submitting", () => {
    render(<AttemptView attemptId="a1" />);
    fireEvent.click(screen.getByLabelText("useState"));
    fireEvent.change(screen.getByLabelText("Answer: Rendering"), { target: { value: "When state changes" } });
    expect(screen.getByText(/2 of 2 answered/)).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(save).toHaveBeenCalledWith({ q1: 1, q2: "When state changes" }, expect.any(Object));
    fireEvent.click(screen.getByRole("button", { name: /Submit test/ }));
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(submit).toHaveBeenCalledOnce();
  });

  it("shows the level, sections and the correct MCQ answer after grading", () => {
    attempt = {
      ...base,
      status: "graded",
      score: 72,
      level: "advanced",
      sections: { mcq: 100, viva: 40 },
      questions: [
        { ...questions[0], content: { options: ["useRef", "useState"], answer: 1, explanation: "useState stores state." }, result: { score: 1 } },
        { ...questions[1], result: { score: 0.4, feedback: "Mention context.", items: [{ key: "p0", description: "State changes", credit: 1 }] } },
      ],
    };
    render(<AttemptView attemptId="a1" />);
    expect(screen.getByText("advanced")).toBeInTheDocument();
    expect(screen.getAllByText("Multiple choice")).toHaveLength(2); // section bar + question badge
    expect(screen.getByText("Correct answer:").parentElement).toHaveTextContent("useState");
    expect(screen.getByText("Mention context.")).toBeInTheDocument();
  });
});

describe("SkillsCard", () => {
  it("lists verified skills and badges", () => {
    render(<SkillsCard />);
    expect(screen.getByText("advanced · 72")).toBeInTheDocument();
    expect(screen.getByText("React practitioner")).toBeInTheDocument();
  });
});
