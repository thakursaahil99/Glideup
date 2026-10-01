"""Audit trail writer. Call `record` inside the same transaction as the change it
describes, so the change and its audit entry commit (or roll back) together."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, User


@dataclass(frozen=True, slots=True)
class RequestMeta:
    ip_address: str | None = None
    user_agent: str | None = None
    request_id: str | None = None


async def record(
    session: AsyncSession,
    *,
    actor: User | None,
    action: str,
    target_type: str | None = None,
    target_id: uuid.UUID | str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    meta: RequestMeta | None = None,
) -> AuditLog:
    meta = meta or RequestMeta()
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        before=before,
        after=after,
        ip_address=meta.ip_address,
        user_agent=(meta.user_agent or "")[:500] or None,
        request_id=meta.request_id,
    )
    session.add(entry)
    await session.flush()
    return entry
