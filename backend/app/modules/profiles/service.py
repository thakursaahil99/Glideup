import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Profile, RemotePreference, User


async def get_or_create(session: AsyncSession, user_id: uuid.UUID) -> Profile:
    profile = await session.get(Profile, user_id)
    if profile is None:
        profile = Profile(
            user_id=user_id,
            target_roles=[],
            preferred_locations=[],
            remote_preference=RemotePreference.ANY,
        )
        session.add(profile)
        await session.flush()
    return profile


def _clean_list(values: list[str], limit: int) -> list[str]:
    seen: dict[str, str] = {}
    for value in values:
        cleaned = " ".join(value.split())[:100]
        if cleaned and cleaned.lower() not in seen:
            seen[cleaned.lower()] = cleaned
    return list(seen.values())[:limit]


async def update(
    session: AsyncSession,
    user: User,
    *,
    name: str | None,
    headline: str | None,
    bio: str | None,
    years_experience: float | None,
    target_roles: list[str],
    preferred_locations: list[str],
    remote_preference: RemotePreference,
    complete_onboarding: bool,
) -> Profile:
    profile = await get_or_create(session, user.id)
    if name is not None and name.strip():
        user.name = name.strip()[:200]
    profile.headline = headline.strip() if headline and headline.strip() else None
    profile.bio = bio.strip() if bio and bio.strip() else None
    profile.years_experience = (
        Decimal(str(years_experience)) if years_experience is not None else None
    )
    profile.target_roles = _clean_list(target_roles, 10)
    profile.preferred_locations = _clean_list(preferred_locations, 10)
    profile.remote_preference = remote_preference
    if complete_onboarding and profile.onboarding_completed_at is None:
        profile.onboarding_completed_at = datetime.now(UTC)
    await session.flush()
    return profile
