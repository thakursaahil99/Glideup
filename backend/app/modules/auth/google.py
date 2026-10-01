"""Verify Google ID tokens against Google's published signing keys.

The frontend (Auth.js) completes the OAuth dance and hands us Google's `id_token`.
We never trust the frontend's word for who the user is: we check the signature,
issuer, audience (our client id), expiry and that the email is verified.
"""

from dataclasses import dataclass
from functools import lru_cache

import anyio
import jwt

from app.core.config import Settings
from app.core.errors import UnauthorizedError

GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    sub: str
    email: str
    name: str | None
    picture: str | None


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> jwt.PyJWKClient:
    # Keys are cached in-process and refetched when an unknown `kid` appears.
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)


def _verify_sync(settings: Settings, id_token: str) -> GoogleIdentity:
    if not settings.google_client_id:
        raise UnauthorizedError("Google sign-in is not configured", code="google_not_configured")
    try:
        signing_key = _jwks_client(settings.google_jwks_url).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.google_client_id,
            issuer=GOOGLE_ISSUERS,
            options={"require": ["sub", "email", "exp", "iat"]},
            leeway=30,
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid Google token", code="invalid_google_token") from exc

    if claims.get("email_verified") is not True:
        raise UnauthorizedError("Google email is not verified", code="email_not_verified")
    return GoogleIdentity(
        sub=str(claims["sub"]),
        email=str(claims["email"]).lower(),
        name=claims.get("name"),
        picture=claims.get("picture"),
    )


async def verify_google_id_token(settings: Settings, id_token: str) -> GoogleIdentity:
    # PyJWKClient does blocking HTTP; keep it off the event loop.
    return await anyio.to_thread.run_sync(_verify_sync, settings, id_token)
