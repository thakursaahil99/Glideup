import { describe, expect, it } from "vitest";

import { diffKeys } from "@/components/admin/audit-log";
import { ApiError, errorMessage, unwrap } from "@/lib/api/client";
import { toCsv } from "@/lib/csv";
import { ADMIN_NAV, hasPermission, isActive, visibleNav } from "@/lib/navigation";
import { humanize, initials } from "@/lib/utils";

describe("navigation permissions", () => {
  it("shows a support user only what support may read", () => {
    const labels = visibleNav(ADMIN_NAV, [
      "admin:access",
      "users:read",
      "audit:read",
      "reports:read",
      "system:read",
    ]).map((i) => i.label);
    expect(labels).toContain("Users");
    expect(labels).toContain("Audit Logs");
    expect(labels).not.toContain("AI / LLM Settings");
    expect(labels).not.toContain("Question Bank");
  });

  it("treats items without a permission as public", () => {
    expect(hasPermission(undefined)).toBe(true);
    expect(hasPermission([], "users:read")).toBe(false);
  });

  it("matches section roots exactly and nested pages by prefix", () => {
    expect(isActive("/admin/users", "/admin")).toBe(false);
    expect(isActive("/admin", "/admin")).toBe(true);
    expect(isActive("/admin/users/123", "/admin/users")).toBe(true);
  });
});

describe("unwrap", () => {
  it("returns data for ok responses", async () => {
    const response = new Response("{}", { status: 200 });
    await expect(unwrap(Promise.resolve({ data: { ok: 1 }, response }))).resolves.toEqual({ ok: 1 });
  });

  it("turns the backend error envelope into an ApiError", async () => {
    const response = new Response("{}", { status: 403 });
    const error = { error: { code: "forbidden", message: "Nope", request_id: "abcdef1234567890" } };
    const thrown = await unwrap(Promise.resolve({ error, response })).catch((e: unknown) => e);
    expect(thrown).toBeInstanceOf(ApiError);
    expect(thrown).toMatchObject({ status: 403, code: "forbidden", message: "Nope" });
    expect(errorMessage(thrown)).toBe("Nope (ref abcdef12)");
  });
});

describe("csv", () => {
  it("quotes special characters and neutralises formulas", () => {
    expect(toCsv(["a", "b"], [["x,y", '=HYPERLINK("evil")']])).toBe('a,b\r\n"x,y","\'=HYPERLINK(""evil"")"');
  });
});

describe("audit diff", () => {
  it("flags only the fields that changed", () => {
    const rows = diffKeys({ roles: ["user"], status: "active" }, { roles: ["admin"], status: "active" });
    expect(rows.filter((r) => r.changed).map((r) => r.key)).toEqual(["roles"]);
  });
});

describe("formatting", () => {
  it("builds initials from a name or an email", () => {
    expect(initials("Sahil Thakur")).toBe("ST");
    expect(initials(null, "pilot.bir@example.com")).toBe("PB");
  });

  it("humanizes identifiers", () => {
    expect(humanize("super_admin")).toBe("Super Admin");
  });
});
