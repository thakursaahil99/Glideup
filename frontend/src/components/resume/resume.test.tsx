import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ParseStatus } from "@/components/resume/parse-status";
import { validateResumeFile } from "@/components/resume/resume-dropzone";
import { groupSkills } from "@/components/resume/skills-editor";
import { TagInput } from "@/components/ui/tag-input";

const mutate = vi.fn();
vi.mock("@/lib/api/hooks", () => ({ useResumeAction: () => ({ mutate, isPending: false }) }));

describe("validateResumeFile", () => {
  it("accepts PDFs and rejects other or oversized files", () => {
    expect(validateResumeFile(new File(["%PDF"], "cv.pdf", { type: "application/pdf" }))).toBeNull();
    expect(validateResumeFile(new File(["x"], "cv.docx", { type: "application/msword" }))).toMatch(/PDF/);
    const huge = new File([new Uint8Array(6 * 1024 * 1024)], "big.pdf", { type: "application/pdf" });
    expect(validateResumeFile(huge)).toMatch(/larger than/);
    expect(validateResumeFile(new File([], "empty.pdf", { type: "application/pdf" }))).toMatch(/empty/);
  });
});

describe("groupSkills", () => {
  it("groups by category in a stable order, with uncategorised skills last", () => {
    const groups = groupSkills([
      { name: "Docker", category: "devops", years: 3 },
      { name: "Python", category: "language", years: 7 },
      { name: "Mentoring", category: null },
      { name: "Go", category: "language" },
    ]);
    expect(groups.map((g) => g.category)).toEqual(["language", "devops", "other"]);
    expect(groups[0].skills.map((s) => s.name)).toEqual(["Python", "Go"]);
  });
});

describe("ParseStatus", () => {
  it("shows progress while parsing", () => {
    render(<ParseStatus resume={{ id: "1", status: "parsing", error: null, parsed_by: null }} />);
    expect(screen.getByText("Reading & extracting skills")).toBeInTheDocument();
    expect(screen.getByText(/usually takes/)).toBeInTheDocument();
  });

  it("shows the error and lets the user retry", () => {
    render(<ParseStatus resume={{ id: "r1", status: "failed", error: "Scanned PDF", parsed_by: null }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Scanned PDF");
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(mutate).toHaveBeenCalledWith("r1", expect.any(Object));
  });

  it("is honest when the offline fallback parsed the resume", () => {
    render(<ParseStatus resume={{ id: "1", status: "parsed", error: null, parsed_by: "mock:mock-1" }} />);
    expect(screen.getByText(/offline fallback/)).toBeInTheDocument();
  });
});

function TagHarness() {
  const [tags, setTags] = useState<string[]>(["Backend Engineer"]);
  return <TagInput label="Add role" value={tags} onChange={setTags} />;
}

describe("TagInput", () => {
  it("adds on Enter, ignores duplicates, removes with the button and Backspace", () => {
    render(<TagHarness />);
    const input = screen.getByRole("textbox", { name: "Add role" });
    fireEvent.change(input, { target: { value: "SRE" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.change(input, { target: { value: "backend engineer" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getAllByRole("button", { name: /Remove/ })).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Remove Backend Engineer" }));
    fireEvent.keyDown(input, { key: "Backspace" });
    expect(screen.queryAllByRole("button", { name: /Remove/ })).toHaveLength(0);
  });
});
