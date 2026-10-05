import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { isGenerating } from "@/components/admin/generation-queue";
import { toInput } from "@/components/admin/question-bank";
import { ProblemSolver } from "@/components/tests/problem-solver";
import { ProblemsList } from "@/components/tests/problems-list";
import type { GenerationItem, ProblemDetail, QuestionAdminDetail, RunResult } from "@/lib/api/types";

const problem: ProblemDetail = {
  slug: "two-sum",
  title: "Two Sum",
  difficulty: "easy",
  topics: ["arrays"],
  statement: "Find **two** numbers.",
  examples: [{ input: "4 9\n2 7 11 15\n", expected_output: "0 1\n" }],
  hidden_tests: 4,
  starters: { python: "import sys\n", go: "package main\n" },
  languages: [
    { key: "python", name: "Python 3", time_limit_s: 3, memory_limit_mb: 256 },
    { key: "go", name: "Go", time_limit_s: 3, memory_limit_mb: 256 },
  ],
};

const runResult: RunResult = {
  verdict: "wrong_answer",
  passed: 0,
  total: 2,
  compile_output: null,
  max_time_ms: 10,
  results: [
    {
      position: 0,
      hidden: false,
      verdict: "wrong_answer",
      input: "4 9",
      expected: "0 1",
      stdout: "1 0",
      time_ms: 10,
    },
    { position: 1, hidden: true, verdict: "accepted", time_ms: 9 },
  ],
};

const run = vi.fn();
const submit = vi.fn();

vi.mock("@/lib/api/problems", async (original) => ({
  ...(await original<typeof import("@/lib/api/problems")>()),
  useProblems: () => ({
    data: [
      {
        slug: "two-sum",
        title: "Two Sum",
        difficulty: "easy",
        topics: ["arrays"],
        solved: true,
        attempted: true,
      },
      {
        slug: "edit-distance",
        title: "Edit Distance",
        difficulty: "hard",
        topics: ["dp"],
        solved: false,
        attempted: false,
      },
    ],
    isPending: false,
    isError: false,
  }),
  useProblem: () => ({ data: problem, isPending: false, isError: false }),
  useRunCode: () => ({ mutate: run, isPending: false, data: runResult }),
  useSubmitCode: () => ({ mutate: submit, isPending: false }),
  useSubmission: () => ({ data: undefined }),
  useMySubmissions: () => ({ data: [] }),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

vi.mock("@/lib/api/skills", () => ({
  useFrameworks: () => ({ data: [], isPending: false, isError: false }),
  useStartAttempt: () => ({ mutate: vi.fn(), isPending: false }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
});

describe("ProblemsList", () => {
  it("shows progress and keeps a preselected language in links", () => {
    render(<ProblemsList language="go" />);
    expect(screen.getByText("1 of 2 solved")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Two Sum/ })).toHaveAttribute("href", "/tests/two-sum?lang=go");
    expect(screen.getByLabelText("Solved")).toBeInTheDocument();
  });
});

describe("ProblemSolver", () => {
  it("starts from the preselected language and runs the examples", () => {
    render(<ProblemSolver slug="two-sum" language="go" />);
    expect(screen.getByLabelText("Language")).toHaveValue("go");
    expect(screen.getByLabelText("Code editor")).toHaveValue("package main\n");
    expect(screen.getByText("two")).toBeInTheDocument(); // markdown bold rendered
    fireEvent.click(screen.getByRole("button", { name: /Run examples/ }));
    expect(run).toHaveBeenCalledWith({ language: "go", code: "package main\n" }, expect.any(Object));
  });

  it("shows details for visible tests only", () => {
    render(<ProblemSolver slug="two-sum" />);
    fireEvent.click(screen.getByRole("button", { name: /Run examples/ }));
    expect(screen.getByText("1 0")).toBeInTheDocument(); // the user's output for the visible test
    expect(screen.getByText("(hidden)")).toBeInTheDocument();
    expect(screen.getAllByText("Input")).toHaveLength(2); // example + the one visible failure
  });

  it("keeps a draft per language and indents with Tab", () => {
    render(<ProblemSolver slug="two-sum" />);
    const editor = screen.getByLabelText("Code editor");
    fireEvent.change(editor, { target: { value: "print(1)" } });
    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "go" } });
    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "python" } });
    expect(screen.getByLabelText("Code editor")).toHaveValue("print(1)");
    fireEvent.keyDown(screen.getByLabelText("Code editor"), { key: "Tab" });
    expect((screen.getByLabelText("Code editor") as HTMLTextAreaElement).value).toContain("    ");
    fireEvent.click(screen.getByRole("button", { name: /Submit/ }));
    expect(submit).toHaveBeenCalledOnce();
  });
});

describe("admin helpers", () => {
  it("polls the queue only while something is generating", () => {
    const item = { status: "ready" } as GenerationItem;
    expect(isGenerating([item])).toBe(false);
    expect(isGenerating([item, { ...item, status: "generating" }])).toBe(true);
  });

  it("turns a stored question into an editable form", () => {
    const q = {
      slug: "x",
      title: "X",
      difficulty: "easy",
      topics: ["a"],
      statement: "s",
      templates: [],
      tests: [{ input: "1", expected_output: "1", hidden: true }],
    } as unknown as QuestionAdminDetail;
    expect(toInput(q)).toMatchObject({ slug: "x", topics: ["a"], tests: [{ input: "1" }] });
  });
});
