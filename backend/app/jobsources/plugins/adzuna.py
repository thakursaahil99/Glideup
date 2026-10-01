"""Adzuna job search API (free developer tier: https://developer.adzuna.com).

Requires ADZUNA_APP_ID and ADZUNA_APP_KEY. Adzuna's terms require attribution, which the UI
shows next to its jobs. Which of Adzuna's countries are read is admin-controlled (Jobs &
Sources). Each (country, search term) pair is one scope, so a failed query never marks
another query's jobs stale.
"""

from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.config import get_settings
from app.jobsources.base import FetchContext, Posting, ScopeResult
from app.jobsources.http import SourceHttpError

# Every country Adzuna's API serves: path code -> (ISO 3166-1, display name, salary currency).
SUPPORTED_COUNTRIES: dict[str, tuple[str, str, str]] = {
    "at": ("AT", "Austria", "EUR"),
    "au": ("AU", "Australia", "AUD"),
    "be": ("BE", "Belgium", "EUR"),
    "br": ("BR", "Brazil", "BRL"),
    "ca": ("CA", "Canada", "CAD"),
    "ch": ("CH", "Switzerland", "CHF"),
    "de": ("DE", "Germany", "EUR"),
    "es": ("ES", "Spain", "EUR"),
    "fr": ("FR", "France", "EUR"),
    "gb": ("GB", "United Kingdom", "GBP"),
    "in": ("IN", "India", "INR"),
    "it": ("IT", "Italy", "EUR"),
    "mx": ("MX", "Mexico", "MXN"),
    "nl": ("NL", "Netherlands", "EUR"),
    "nz": ("NZ", "New Zealand", "NZD"),
    "pl": ("PL", "Poland", "PLN"),
    "sg": ("SG", "Singapore", "SGD"),
    "us": ("US", "United States", "USD"),
    "za": ("ZA", "South Africa", "ZAR"),
}

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
MAX_QUERIES = 20
MAX_PAGES = 5


class AdzunaPlugin:
    key = "adzuna"
    name = "Adzuna"
    uses_company_boards = False
    attribution: str | None = "Jobs by Adzuna"

    def is_configured(self, config: dict[str, Any]) -> str | None:
        settings = get_settings()
        if not (settings.adzuna_app_id and settings.adzuna_app_key):
            return "Set ADZUNA_APP_ID and ADZUNA_APP_KEY (free at developer.adzuna.com)"
        if not self.validate_config(config)["countries"]:
            return "Choose at least one country"
        return None

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        merged = {**DEFAULT_CONFIG, **(config or {})}
        unknown_keys = set(config or {}) - set(DEFAULT_CONFIG)
        if unknown_keys:
            raise ValueError(f"Unknown setting(s): {', '.join(sorted(unknown_keys))}")

        countries = merged["countries"]
        if not isinstance(countries, list) or not all(isinstance(c, str) for c in countries):
            raise ValueError("countries must be a list of country codes")
        countries = list(dict.fromkeys(c.strip().lower() for c in countries))
        unsupported = [c for c in countries if c not in SUPPORTED_COUNTRIES]
        if unsupported:
            raise ValueError(
                f"Adzuna does not support: {', '.join(unsupported)}. "
                f"Supported: {', '.join(sorted(SUPPORTED_COUNTRIES))}"
            )

        queries = merged["queries"]
        if not isinstance(queries, list) or not all(isinstance(q, str) for q in queries):
            raise ValueError("queries must be a list of search terms")
        queries = [" ".join(q.split())[:100] for q in queries if q.strip()]
        if not queries or len(queries) > MAX_QUERIES:
            raise ValueError(f"Provide between 1 and {MAX_QUERIES} search terms")

        try:
            pages = int(merged["pages_per_query"])
            days = int(merged["max_days_old"])
        except (TypeError, ValueError) as exc:
            raise ValueError("pages_per_query and max_days_old must be numbers") from exc
        if not 1 <= pages <= MAX_PAGES:
            raise ValueError(f"pages_per_query must be between 1 and {MAX_PAGES}")
        if not 1 <= days <= 90:
            raise ValueError("max_days_old must be between 1 and 90")
        return {
            "countries": countries,
            "queries": queries,
            "pages_per_query": pages,
            "max_days_old": days,
        }

    def config_options(self) -> dict[str, Any] | None:
        return {
            "supported_countries": [
                {"code": code, "name": name}
                for code, (_, name, _) in sorted(
                    SUPPORTED_COUNTRIES.items(), key=lambda kv: kv[1][1]
                )
            ],
            "defaults": DEFAULT_CONFIG,
        }

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[ScopeResult]:
        settings = get_settings()
        config = self.validate_config(ctx.config)
        app_key = settings.adzuna_app_key.get_secret_value() if settings.adzuna_app_key else ""
        for country in config["countries"]:
            for query in config["queries"]:
                scope = f"adzuna:{country}:{query}"
                postings: list[Posting] = []
                try:
                    for page in range(1, config["pages_per_query"] + 1):
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
                        postings.extend(posting_from_adzuna(job, country) for job in results)
                        if len(results) < 50:
                            break
                except SourceHttpError as exc:
                    yield ScopeResult(scope, complete=False, error=str(exc))
                    continue
                yield ScopeResult(scope, postings)


def posting_from_adzuna(job: dict[str, Any], country: str) -> Posting:
    iso, _, currency = SUPPORTED_COUNTRIES[country]
    company = (job.get("company") or {}).get("display_name") or "Unknown company"
    location = job.get("location") or {}
    contract = job.get("contract_time")
    created = job.get("created")
    return Posting(
        external_id=str(job["id"]),
        title=job.get("title") or "Untitled role",
        company_name=company,
        apply_url=job.get("redirect_url") or "",
        # Adzuna only provides a snippet; the full posting is on the employer/board page.
        description_html=f"<p>{job.get('description') or ''}</p>",
        location=location.get("display_name"),
        country=iso,
        # e.g. ["India", "Karnataka", "Bangalore"]: structured, better than the display name.
        region_hint=[str(a) for a in location.get("area") or []] or None,
        employment_type={"full_time": "Full-time", "part_time": "Part-time"}.get(contract or ""),
        posted_at=datetime.fromisoformat(created.replace("Z", "+00:00")) if created else None,
        salary_min=Decimal(str(job["salary_min"])) if job.get("salary_min") else None,
        salary_max=Decimal(str(job["salary_max"])) if job.get("salary_max") else None,
        salary_currency=currency if job.get("salary_min") else None,
        salary_period="year" if job.get("salary_min") else None,
    )
