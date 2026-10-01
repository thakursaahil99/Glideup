"""ATS job-board plugins: public, documented APIs that companies publish for their own
careers pages. We only read what each company already publishes, and every job links to
the company's official application page.

- Greenhouse: https://developers.greenhouse.io/job-board.html
- Lever:      https://github.com/lever/postings-api
- Ashby:      https://developers.ashbyhq.com/docs/public-job-posting-api
"""

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.jobsources.base import BoardTarget, FetchContext, Posting, ScopeResult
from app.jobsources.geo import guess_country
from app.jobsources.http import SourceHttpError


def _dt(value: Any) -> datetime | None:
    if isinstance(value, int | float):  # epoch milliseconds (Lever)
        return datetime.fromtimestamp(value / 1000, UTC)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except InvalidOperation:
        return None


class _ATSPlugin:
    key = ""
    name = ""
    uses_company_boards = True
    attribution: str | None = None

    def is_configured(self, config: dict[str, Any]) -> str | None:
        return None

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        if config:
            raise ValueError("This source has no settings; manage its companies instead.")
        return {}

    def config_options(self) -> dict[str, Any] | None:
        return None

    async def _read_board(self, ctx: FetchContext, board: BoardTarget) -> list[Posting]:
        raise NotImplementedError

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[ScopeResult]:
        for board in ctx.boards:
            scope = f"{self.key}:{board.board_token}"
            try:
                postings = await self._read_board(ctx, board)
            except SourceHttpError as exc:
                yield ScopeResult(
                    scope, company_id=board.company_id, complete=False, error=str(exc)
                )
                continue
            yield ScopeResult(scope, postings, company_id=board.company_id)


class GreenhousePlugin(_ATSPlugin):
    key = "greenhouse"
    name = "Greenhouse job boards"

    async def _read_board(self, ctx: FetchContext, board: BoardTarget) -> list[Posting]:
        data = await ctx.http.get_json(
            f"https://boards-api.greenhouse.io/v1/boards/{board.board_token}/jobs",
            params={"content": "true"},
        )
        postings = []
        for job in data.get("jobs", []):
            location = (job.get("location") or {}).get("name")
            departments = [d.get("name") for d in job.get("departments") or [] if d.get("name")]
            postings.append(
                Posting(
                    external_id=str(job["id"]),
                    title=job.get("title") or "Untitled role",
                    company_name=board.name,  # our verified name, not the board's free text
                    apply_url=job["absolute_url"],
                    description_html=job.get("content") or "",
                    location=location,
                    country=guess_country(location),
                    department=departments[0] if departments else None,
                    posted_at=_dt(job.get("first_published")) or _dt(job.get("updated_at")),
                )
            )
        return postings


class LeverPlugin(_ATSPlugin):
    key = "lever"
    name = "Lever job boards"

    async def _read_board(self, ctx: FetchContext, board: BoardTarget) -> list[Posting]:
        data = await ctx.http.get_json(
            f"https://api.lever.co/v0/postings/{board.board_token}", params={"mode": "json"}
        )
        postings = []
        for job in data if isinstance(data, list) else []:
            categories = job.get("categories") or {}
            # Lever splits a posting into an intro, titled lists and a closing section.
            sections = [job.get("description") or ""]
            for item in job.get("lists") or []:
                sections.append(
                    f"<h3>{item.get('text', '')}</h3><ul>{item.get('content', '')}</ul>"
                )
            sections.append(job.get("additional") or "")
            salary = job.get("salaryRange") or {}
            workplace = job.get("workplaceType")
            postings.append(
                Posting(
                    external_id=str(job["id"]),
                    title=job.get("text") or "Untitled role",
                    company_name=board.name,
                    apply_url=job.get("hostedUrl") or job.get("applyUrl"),
                    description_html="\n".join(sections),
                    location=categories.get("location"),
                    country=(job.get("country") or None)
                    or guess_country(categories.get("location")),
                    workplace_hint=workplace if workplace != "unspecified" else None,
                    employment_type=categories.get("commitment"),
                    department=categories.get("team") or categories.get("department"),
                    posted_at=_dt(job.get("createdAt")),
                    salary_min=_decimal(salary.get("min")),
                    salary_max=_decimal(salary.get("max")),
                    salary_currency=salary.get("currency"),
                    salary_period=_period(salary.get("interval")),
                )
            )
        return postings


def _period(interval: Any) -> str | None:
    text = str(interval or "").lower()
    for word, period in (
        ("year", "year"),
        ("annual", "year"),
        ("month", "month"),
        ("hour", "hour"),
    ):
        if word in text:
            return period
    return None


class AshbyPlugin(_ATSPlugin):
    key = "ashby"
    name = "Ashby job boards"

    async def _read_board(self, ctx: FetchContext, board: BoardTarget) -> list[Posting]:
        data = await ctx.http.get_json(
            f"https://api.ashbyhq.com/posting-api/job-board/{board.board_token}",
            params={"includeCompensation": "true"},
        )
        postings = []
        for job in data.get("jobs", []):
            if job.get("isListed") is False:
                continue
            salary = _ashby_salary(job.get("compensation") or {})
            country = ((job.get("address") or {}).get("postalAddress") or {}).get("addressCountry")
            location = job.get("location")
            postings.append(
                Posting(
                    external_id=str(job["id"]),
                    title=job.get("title") or "Untitled role",
                    company_name=board.name,
                    apply_url=job.get("jobUrl") or job.get("applyUrl"),
                    description_html=job.get("descriptionHtml") or "",
                    location=location,
                    country=guess_country(country) or guess_country(location),
                    remote_hint=job.get("isRemote"),
                    workplace_hint=job.get("workplaceType"),
                    employment_type=_employment(job.get("employmentType")),
                    department=job.get("team") or job.get("department"),
                    posted_at=_dt(job.get("publishedAt")),
                    **salary,
                )
            )
        return postings


def _employment(value: Any) -> str | None:
    mapping = {"FullTime": "Full-time", "PartTime": "Part-time", "Intern": "Internship"}
    return mapping.get(str(value), str(value) if value else None)


def _ashby_salary(compensation: dict[str, Any]) -> dict[str, Any]:
    for part in compensation.get("summaryComponents") or []:
        if str(part.get("compensationType", "")).lower() == "salary":
            return {
                "salary_min": _decimal(part.get("minValue")),
                "salary_max": _decimal(part.get("maxValue")),
                "salary_currency": part.get("currencyCode"),
                "salary_period": _period(part.get("interval")),
            }
    return {}


ATS_PLUGINS: dict[str, Callable[[], _ATSPlugin]] = {
    "greenhouse": GreenhousePlugin,
    "lever": LeverPlugin,
    "ashby": AshbyPlugin,
}
