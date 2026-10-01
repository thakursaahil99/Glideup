"""Liveness and readiness probes (used by Docker healthchecks and, later, Azure)."""

import asyncio
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text

from app.api.deps import SettingsDep
from app.db.session import session_factory

router = APIRouter(tags=["health"])

CHECK_TIMEOUT_SECONDS = 2.0


class Liveness(BaseModel):
    status: Literal["ok"] = "ok"


class Readiness(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, str]


@router.get("/healthz", response_model=Liveness)
async def liveness() -> Liveness:
    """The process is up. Deliberately checks nothing else."""
    return Liveness()


async def _check_db() -> None:
    async with session_factory()() as session:
        await session.execute(text("SELECT 1"))


async def _check_redis(url: str) -> None:
    client = Redis.from_url(url)
    try:
        await client.ping()
    finally:
        await client.aclose()


@router.get("/readyz", response_model=Readiness, responses={503: {"model": Readiness}})
async def readiness(settings: SettingsDep) -> JSONResponse:
    """Dependencies the API cannot serve without are reachable."""
    checks: dict[str, str] = {}
    for name, probe in (("database", _check_db()), ("redis", _check_redis(settings.redis_url))):
        try:
            await asyncio.wait_for(probe, CHECK_TIMEOUT_SECONDS)
            checks[name] = "ok"
        except Exception as exc:  # any failure means "not ready"; the reason is reported
            checks[name] = f"error: {type(exc).__name__}"
    ok = all(v == "ok" for v in checks.values())
    body = Readiness(status="ok" if ok else "degraded", checks=checks)
    return JSONResponse(status_code=200 if ok else 503, content=body.model_dump())
