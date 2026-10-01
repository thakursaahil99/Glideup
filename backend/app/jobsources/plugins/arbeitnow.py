"""Arbeitnow public job board API (free, no key): https://www.arbeitnow.com/api/job-board-api

Mostly Europe (Germany, UK, Switzerland, France) plus remote roles. Each page is one scope,
so one failing page never retires jobs from the others.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from app.jobsources.base import FetchContext, Posting, ScopeResult
from app.jobsources.http import SourceHttpError

DEFAULT_CONFIG: dict[str, Any] = {"max_pages": 5}
URL = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowPlugin:
    key = "arbeitnow"
    name = "Arbeitnow"
    uses_company_boards = False
    attribution: str | None = "Jobs via Arbeitnow"

    def is_configured(self, config: dict[str, Any]) -> str | None:
        return None

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        unknown = set(config or {}) - set(DEFAULT_CONFIG)
        if unknown:
            raise ValueError(f"Unknown setting(s): {', '.join(sorted(unknown))}")
        try:
            pages = int({**DEFAULT_CONFIG, **(config or {})}["max_pages"])
        except (TypeError, ValueError) as exc:
            raise ValueError("max_pages must be a number") from exc
        if not 1 <= pages <= 20:
            raise ValueError("max_pages must be between 1 and 20")
        return {"max_pages": pages}

    def config_options(self) -> dict[str, Any] | None:
        return {"defaults": DEFAULT_CONFIG}

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[ScopeResult]:
        config = self.validate_config(ctx.config)
        for page in range(1, config["max_pages"] + 1):
            scope = f"arbeitnow:page-{page}"
            try:
                data = await ctx.http.get_json(URL, params={"page": page})
            except SourceHttpError as exc:
                yield ScopeResult(scope, complete=False, error=str(exc))
                break
            jobs = data.get("data") or []
            yield ScopeResult(scope, [posting_from_arbeitnow(job) for job in jobs])
            if not (data.get("links") or {}).get("next") or not jobs:
                break


def posting_from_arbeitnow(job: dict[str, Any]) -> Posting:
    created = job.get("created_at")
    remote = job.get("remote") in (True, "true", "True")
    job_types = job.get("job_types") or []
    return Posting(
        external_id=str(job["slug"]),
        title=job.get("title") or "Untitled role",
        company_name=job.get("company_name") or "Unknown company",
        apply_url=job.get("url") or "",
        description_html=job.get("description") or "",
        location=job.get("location") or None,
        remote_hint=True if remote else None,
        employment_type=job_types[0] if isinstance(job_types, list) and job_types else None,
        posted_at=datetime.fromtimestamp(int(created), UTC) if created else None,
    )
