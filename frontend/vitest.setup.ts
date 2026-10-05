import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// `server-only` throws outside a React Server environment; tests import server modules directly.
vi.mock("server-only", () => ({}));

afterEach(() => cleanup());

// Feature flags default to "on" (as in production while loading); tests that care override this.
vi.mock("@/lib/api/platform", () => ({
  useFlags: () => ({ data: undefined }),
  useFlag: () => true,
  useAnnouncements: () => ({ data: [] }),
}));
