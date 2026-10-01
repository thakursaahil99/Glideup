"""Adzuna job search API (free developer tier: https://developer.adzuna.com).

Requires ADZUNA_APP_ID and ADZUNA_APP_KEY. Adzuna's terms require attribution, which the UI
shows next to its jobs. Each (country, search term) pair is one scope, so a failed query
never marks another query's jobs stale.
"""

from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.config import get_settings
from app.jobsources.base import FetchContext, Posting, ScopeResult
from app.jobsources.http import SourceHttpError

DEFAULT_CONFIG: dict[str, Any] = {
    "countries": ["in"],
    "queries": [
        "software engineer",
        "full stack developer",
        "backend developer",
        "frontend developer",
        "data engineer",
        "devops engineer",
    ],
    "pages_per_query": 2,
    "max_days_old": 30,
}


class AdzunaPlugin:
    key = "adzuna"
    name = "Adzuna"
    uses_company_boards = False
    attribution: str | None = "Jobs by Adzuna"

    def is_configured(self, config: dict[str, Any]) -> str | None:
        settings = get_settings()
        if not (settings.adzuna_app_id and settings.adzuna_app_key):
            return "Set ADZUNA_APP_ID and ADZUNA_APP_KEY (free at developer.adzuna.com)"
        return None

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[ScopeResult]:
        settings = get_settings()
        config = {**DEFAULT_CONFIG, **ctx.config}
        app_key = settings.adzuna_app_key.get_secret_value() if settings.adzuna_app_key else ""
        for country in config["countries"]:
            for query in config["queries"]:
                scope = f"adzuna:{country}:{query}"
                postings: list[Posting] = []
                try:
                    for page in range(1, int(config["pages_per_query"]) + 1):
                        data = await ctx.http.get_json(
                            f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}",
                            params={
                                "app_id": settings.adzuna_app_id,
                                "app_key": app_key,
                                "what": query,
                                "results_per_page": 50,
                                "max_days_old": config["max_days_old"],
                                "content-type": "application/json",
                            },
                        )
                        results = data.get("results") or []
                        postings.extend(_posting(job, country) for job in results)
                        if len(results) < 50:
                            break
                except SourceHttpError as exc:
                    yield ScopeResult(scope, complete=False, error=str(exc))
                    continue
                yield ScopeResult(scope, postings)


def _posting(job: dict[str, Any], country: str) -> Posting:
    company = (job.get("company") or {}).get("display_name") or "Unknown company"
    location = (job.get("location") or {}).get("display_name")
    contract = job.get("contract_time")
    created = job.get("created")
    return Posting(
        external_id=str(job["id"]),
        title=job.get("title") or "Untitled role",
        company_name=company,
        apply_url=job.get("redirect_url") or "",
        # Adzuna only provides a snippet; the full posting is on the employer/board page.
        description_html=f"<p>{job.get('description') or ''}</p>",
        location=location,
        country=country.upper(),
        employment_type={"full_time": "Full-time", "part_time": "Part-time"}.get(contract or ""),
        posted_at=datetime.fromisoformat(created.replace("Z", "+00:00")) if created else None,
        salary_min=Decimal(str(job["salary_min"])) if job.get("salary_min") else None,
        salary_max=Decimal(str(job["salary_max"])) if job.get("salary_max") else None,
        salary_currency={"in": "INR", "gb": "GBP", "us": "USD"}.get(country),
        salary_period="year" if job.get("salary_min") else None,
    )
