"""Role-based access control.

Roles live in the `roles` table (so admins can see and assign them), but the
role -> permission mapping lives in code: permissions are what the code checks,
so changing them is a code change that goes through review, tests and the audit trail.
Endpoints always check a *permission*, never a role name.
"""

from collections.abc import Iterable
from enum import StrEnum


class Role(StrEnum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    CONTENT_EDITOR = "content_editor"
    SUPPORT = "support"
    USER = "user"


class Permission(StrEnum):
    ADMIN_ACCESS = "admin:access"
    USERS_READ = "users:read"
    USERS_WRITE = "users:write"
    ROLES_ASSIGN = "roles:assign"  # grant user / support / content_editor
    ROLES_ASSIGN_ADMIN = "roles:assign_admin"  # grant admin / super_admin
    AUDIT_READ = "audit:read"
    JOBS_MANAGE = "jobs:manage"
    QUESTIONS_MANAGE = "questions:manage"
    PROMPTS_MANAGE = "prompts:manage"
    INTERVIEWS_MANAGE = "interviews:manage"
    CONTENT_MANAGE = "content:manage"
    ANNOUNCEMENTS_MANAGE = "announcements:manage"
    REPORTS_READ = "reports:read"
    REPORTS_MANAGE = "reports:manage"
    LLM_MANAGE = "llm:manage"
    FLAGS_MANAGE = "flags:manage"
    SYSTEM_READ = "system:read"
    SYSTEM_MANAGE = "system:manage"  # retry failed background jobs


ROLE_DESCRIPTIONS: dict[Role, str] = {
    Role.SUPER_ADMIN: "Everything, including managing admins, LLM settings and feature flags",
    Role.ADMIN: "Users, jobs, question bank, interviews, content and announcements",
    Role.CONTENT_EDITOR: "Questions, tests, prompt templates and MCQs — no user management",
    Role.SUPPORT: "Read-only access to users, reports and logs",
    Role.USER: "Normal app access",
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.SUPER_ADMIN: frozenset(Permission),
    Role.ADMIN: frozenset(
        {
            Permission.ADMIN_ACCESS,
            Permission.USERS_READ,
            Permission.USERS_WRITE,
            Permission.ROLES_ASSIGN,
            Permission.AUDIT_READ,
            Permission.JOBS_MANAGE,
            Permission.QUESTIONS_MANAGE,
            Permission.PROMPTS_MANAGE,
            Permission.INTERVIEWS_MANAGE,
            Permission.CONTENT_MANAGE,
            Permission.ANNOUNCEMENTS_MANAGE,
            Permission.REPORTS_READ,
            Permission.REPORTS_MANAGE,
            Permission.SYSTEM_READ,
            Permission.SYSTEM_MANAGE,
        }
    ),
    Role.CONTENT_EDITOR: frozenset(
        {
            Permission.ADMIN_ACCESS,
            Permission.QUESTIONS_MANAGE,
            Permission.PROMPTS_MANAGE,
            Permission.INTERVIEWS_MANAGE,
        }
    ),
    Role.SUPPORT: frozenset(
        {
            Permission.ADMIN_ACCESS,
            Permission.USERS_READ,
            Permission.REPORTS_READ,
            Permission.AUDIT_READ,
            Permission.SYSTEM_READ,
        }
    ),
    Role.USER: frozenset(),
}

# Higher rank = more privileged. Used to stop lower roles acting on higher ones.
ROLE_RANK: dict[Role, int] = {
    Role.USER: 0,
    Role.SUPPORT: 1,
    Role.CONTENT_EDITOR: 1,
    Role.ADMIN: 2,
    Role.SUPER_ADMIN: 3,
}

ADMIN_ROLES: frozenset[Role] = frozenset({Role.ADMIN, Role.SUPER_ADMIN})


def _known(roles: Iterable[str]) -> list[Role]:
    # Unknown role names (e.g. left over in the DB) grant nothing.
    return [Role(name) for name in roles if name in Role]


def permissions_for(roles: Iterable[str]) -> frozenset[Permission]:
    granted: set[Permission] = set()
    for role in _known(roles):
        granted |= ROLE_PERMISSIONS[role]
    return frozenset(granted)


def highest_rank(roles: Iterable[str]) -> int:
    return max((ROLE_RANK[role] for role in _known(roles)), default=0)


def permission_required_to_assign(role: Role) -> Permission:
    return Permission.ROLES_ASSIGN_ADMIN if role in ADMIN_ROLES else Permission.ROLES_ASSIGN
