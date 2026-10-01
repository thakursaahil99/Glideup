import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Logo } from "@/components/brand/logo";
import { AppShell } from "@/components/layout/app-shell";
import { EmptyState, ErrorState } from "@/components/states";
import { ApiError } from "@/lib/api/client";

vi.mock("next/navigation", () => ({ usePathname: () => "/admin/users" }));
vi.mock("next-auth/react", () => ({ signOut: vi.fn() }));
vi.mock("next-themes", () => ({ useTheme: () => ({ theme: "light", setTheme: vi.fn() }) }));

const supportUser = {
  name: "Help Desk",
  email: "help@example.com",
  roles: ["support"],
  permissions: ["admin:access", "users:read", "audit:read", "reports:read", "system:read"],
};

describe("Logo", () => {
  it("renders the GlideUp wordmark", () => {
    render(<Logo />);
    expect(screen.getByText(/Glide/)).toHaveTextContent("GlideUp");
  });
});

describe("AppShell (admin)", () => {
  it("only lists admin sections the user is permitted to see", () => {
    render(
      <AppShell variant="admin" user={supportUser}>
        <p>content</p>
      </AppShell>,
    );
    const nav = screen.getByRole("navigation", { name: "Admin" });
    expect(within(nav).getByRole("link", { name: "Users" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Audit Logs" })).toBeInTheDocument();
    expect(within(nav).queryByText("Feature Flags")).not.toBeInTheDocument();
    expect(within(nav).queryByText("Question Bank")).not.toBeInTheDocument();
  });

  it("marks unreleased sections as coming soon instead of linking to them", () => {
    render(
      <AppShell variant="admin" user={supportUser}>
        <p>content</p>
      </AppShell>,
    );
    const nav = screen.getByRole("navigation", { name: "Admin" });
    expect(within(nav).queryByRole("link", { name: /System Health/ })).not.toBeInTheDocument();
    expect(within(nav).getByTitle("Coming in phase 9")).toHaveTextContent("System Health");
  });
});

describe("states", () => {
  it("shows helpful empty states", () => {
    render(<EmptyState title="No users found" body="Try a different search." />);
    expect(screen.getByText("No users found")).toBeInTheDocument();
  });

  it("shows the API error message and a retry button", () => {
    const retry = vi.fn();
    render(<ErrorState error={new ApiError(502, "backend_unreachable", "API down")} onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("API down");
    screen.getByRole("button", { name: /try again/i }).click();
    expect(retry).toHaveBeenCalledOnce();
  });
});
