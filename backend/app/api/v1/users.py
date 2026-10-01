from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.api.v1.profile_schemas import ProfileOut, ProfileUpdate
from app.api.v1.schemas import MeResponse
from app.core.rbac import permissions_for
from app.db.models import Profile, User
from app.modules.profiles import service as profiles
from app.modules.resumes import service as resumes

router = APIRouter(prefix="/users", tags=["users"])


def to_me_response(user: User) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        status=user.status,
        role_names=user.role_names,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        permissions=sorted(permissions_for(user.role_names)),
    )


def to_profile_out(user: User, profile: Profile, *, has_resume: bool) -> ProfileOut:
    return ProfileOut(
        name=user.name,
        email=user.email,
        headline=profile.headline,
        bio=profile.bio,
        years_experience=float(profile.years_experience)
        if profile.years_experience is not None
        else None,
        target_roles=profile.target_roles,
        preferred_locations=profile.preferred_locations,
        remote_preference=profile.remote_preference,
        onboarding_completed=profile.onboarding_completed_at is not None,
        has_resume=has_resume,
    )


@router.get("/me", response_model=MeResponse)
async def read_me(user: CurrentUser) -> MeResponse:
    return to_me_response(user)


@router.get("/me/profile", response_model=ProfileOut)
async def read_profile(session: SessionDep, user: CurrentUser) -> ProfileOut:
    profile = await profiles.get_or_create(session, user.id)
    has_resume = await resumes.get_active(session, user.id) is not None
    return to_profile_out(user, profile, has_resume=has_resume)


@router.put("/me/profile", response_model=ProfileOut)
async def update_profile(body: ProfileUpdate, session: SessionDep, user: CurrentUser) -> ProfileOut:
    profile = await profiles.update(
        session,
        user,
        name=body.name,
        headline=body.headline,
        bio=body.bio,
        years_experience=body.years_experience,
        target_roles=body.target_roles,
        preferred_locations=body.preferred_locations,
        remote_preference=body.remote_preference,
        complete_onboarding=body.complete_onboarding,
    )
    has_resume = await resumes.get_active(session, user.id) is not None
    return to_profile_out(user, profile, has_resume=has_resume)
