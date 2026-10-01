from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.api.v1.schemas import MeResponse
from app.core.rbac import permissions_for
from app.db.models import User

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


@router.get("/me", response_model=MeResponse)
async def read_me(user: CurrentUser) -> MeResponse:
    return to_me_response(user)
