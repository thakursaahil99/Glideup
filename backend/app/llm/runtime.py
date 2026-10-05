"""Admin-editable LLM settings, read at runtime (AI / LLM Settings in the admin console).

Values live in `site_settings` and are cached in-process for REFRESH_S, so a change takes
effect on every worker within that time without a redeploy. Anything not set falls back to
environment settings and code defaults.
"""

import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

REFRESH_S = 30.0

DEFAULTS: dict[str, Any] = {
    "llm.routes": {},  # task -> ["provider:model", ...] overrides
    "llm.cache_enabled": True,
    "llm.cache_ttl_hours": 24,
    "llm.user_daily_token_budget": 0,  # 0 = unlimited
}

_values: dict[str, Any] = dict(DEFAULTS)
_loaded_at = -REFRESH_S


def get(key: str) -> Any:
    return _values.get(key, DEFAULTS.get(key))


def route_overrides() -> dict[str, list[str]]:
    routes = get("llm.routes")
    return routes if isinstance(routes, dict) else {}


def apply(values: dict[str, Any]) -> None:
    """Replace the snapshot (used after an admin change, and by tests)."""
    global _values, _loaded_at
    _values = {**DEFAULTS, **{k: v for k, v in values.items() if k in DEFAULTS}}
    _loaded_at = time.monotonic()


def invalidate() -> None:
    global _loaded_at
    _loaded_at = -REFRESH_S


async def ensure_fresh() -> None:
    if time.monotonic() - _loaded_at < REFRESH_S:
        return
    try:
        from sqlalchemy import select

        from app.db.models import SiteSetting
        from app.db.session import session_factory

        async with session_factory()() as session:
            rows = await session.scalars(
                select(SiteSetting).where(SiteSetting.key.in_(list(DEFAULTS)))
            )
            apply({row.key: row.value for row in rows})
    except Exception:  # settings are an override; never fail an LLM call because of them
        logger.warning("llm_runtime_settings_unavailable", exc_info=True)
        apply(dict(_values))
