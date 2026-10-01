"""Operator (command-line) account management.

For people with shell access to the deployment: bootstrap the first admin in production
(where dev login is off), recover from a locked-out admin team, or audit who has access.
Every change is written to the audit log with `source: cli`, just like changes made in the UI.
"""

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.rbac import Role
from app.db.models import Role as RoleModel
from app.db.models import User, UserRole
from app.modules.audit import service as audit
from app.modules.auth.service import ensure_roles

CLI_SOURCE = {"source": "cli"}


@dataclass(frozen=True, slots=True)
class AccountRow:
    email: str
    name: str | None
    roles: list[str]
    status: str
    has_signed_in: bool


async def set_role(
    session: AsyncSession, *, email: str, role: Role, name: str | None = None, create: bool = True
) -> tuple[User, bool]:
    """Give `email` exactly `role`. Creates the account if needed (it is linked to Google
    on first sign-in, by email). Returns (user, created)."""
    email = email.strip().lower()
    user = await session.scalar(select(User).where(User.email == email))
    created = user is None
    if user is None:
        if not create:
            raise NotFoundError(f"No account for {email}")
        user = User(email=email, name=name)
        session.add(user)
        await session.flush()
        await audit.record(
            session,
            actor=None,
            action="user.created",
            target_type="user",
            target_id=user.id,
            after={"email": email, **CLI_SOURCE},
        )
    await session.refresh(user, ["roles"])
    before = user.role_names
    if before == [role.value]:
        return user, created

    if Role.SUPER_ADMIN.value in before and role != Role.SUPER_ADMIN:
        others = await session.scalar(
            select(UserRole.user_id)
            .join(RoleModel, RoleModel.id == UserRole.role_id)
            .where(RoleModel.name == Role.SUPER_ADMIN.value, UserRole.user_id != user.id)
            .limit(1)
        )
        if others is None:
            raise ConflictError("Refusing to remove the last super_admin", code="last_super_admin")

    roles = await ensure_roles(session)
    await session.execute(delete(UserRole).where(UserRole.user_id == user.id))
    session.add(UserRole(user_id=user.id, role_id=roles[role.value].id))
    await session.flush()
    await session.refresh(user, ["roles"])
    await audit.record(
        session,
        actor=None,
        action="user.role_changed",
        target_type="user",
        target_id=user.id,
        before={"roles": before},
        after={"roles": user.role_names, **CLI_SOURCE},
    )
    return user, created


async def list_staff(session: AsyncSession) -> list[AccountRow]:
    """Everyone with a role other than plain `user`."""
    staff_roles = [r.value for r in Role if r != Role.USER]
    users = await session.scalars(
        select(User)
        .where(
            User.id.in_(
                select(UserRole.user_id)
                .join(RoleModel, RoleModel.id == UserRole.role_id)
                .where(RoleModel.name.in_(staff_roles))
            )
        )
        .order_by(User.email)
    )
    return [
        AccountRow(
            email=u.email,
            name=u.name,
            roles=u.role_names,
            status=u.status.value,
            has_signed_in=u.last_login_at is not None,
        )
        for u in users
    ]
