import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnnouncementBanner } from "@/components/layout/announcement-banner";
import type { Announcement } from "@/lib/api/types";

const announcements: Announcement[] = [
  {
    id: "a1",
    title: "Maintenance tonight",
    body: "Back by 2am.",
    level: "warning",
    audience: "all",
    starts_at: null,
    ends_at: null,
    active: true,
    created_at: "2026-10-05T00:00:00Z",
  },
];

vi.mock("@/lib/api/platform", () => ({
  useAnnouncements: () => ({ data: announcements }),
  useFlag: () => true,
}));

describe("AnnouncementBanner", () => {
  beforeEach(() => window.localStorage.clear());

  it("shows active announcements and remembers dismissals", () => {
    const { unmount } = render(<AnnouncementBanner />);
    expect(screen.getByText("Maintenance tonight")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /dismiss: maintenance tonight/i }));
    expect(screen.queryByText("Maintenance tonight")).not.toBeInTheDocument();
    unmount();
    render(<AnnouncementBanner />);
    expect(screen.queryByText("Maintenance tonight")).not.toBeInTheDocument();
  });
});
