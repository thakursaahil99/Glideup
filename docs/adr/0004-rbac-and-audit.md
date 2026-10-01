# ADR 0004 — RBAC with permissions in code, roles in the database, audit in-transaction

- **Status:** Accepted (Phase 1)
- **Date:** 2026-10-01

## Context
Five roles (`super_admin`, `admin`, `content_editor`, `support`, `user`) must be enforced on
the backend for every admin endpoint, admin access must be granted only via an allowlist or by
a super_admin, and every admin action must be audited with before/after values.

## Decision
- **Endpoints check permissions, never role names** (`require_permission(Permission.USERS_WRITE)`).
- The **role → permission map lives in code** (`app/core/rbac.py`): it is what the code relies
  on, so changes go through review, tests and CI. Roles are rows in `roles`/`user_roles` so
  admins can see and assign them in the UI.
- Guard rails in the service layer: no self-modification; you cannot act on a user with a higher
  role; granting `admin`/`super_admin` needs `roles:assign_admin` (super_admin only); the last
  super_admin cannot be demoted.
- The **only bootstrap path** to admin is `ADMIN_EMAILS`; the grant is itself audited.
- `audit.record(...)` is called **inside the same transaction** as the change, so a change
  without an audit entry (or vice versa) cannot be committed. `actor_email` is denormalised so
  the trail survives account deletion.
- The UI hides what you cannot do and returns 404 for admin pages you cannot access, but that is
  convenience only; the API is the control.

## Consequences
- ✅ Simple to reason about and to test (permission matrix is unit-tested).
- ⚠️ Adding a permission is a code change — intended. Fully custom roles are out of scope.
