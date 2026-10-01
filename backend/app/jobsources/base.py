"""Job source plugin contract.

A plugin knows how to read ONE kind of source (an ATS like Greenhouse, or an aggregator
like Adzuna) and turn its postings into `Posting`s. Everything else — rate limiting,
retries, normalisation, dedup, stale detection, search indexing — is shared.

Adding a source = one new module implementing `JobSourcePlugin` + one registry line.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from app.jobsources.http import SourceHttpClient


@dataclass(slots=True)
class Posting:
    """A job as read from a source, before shared normalisation."""

    external_id: str
    title: str
    company_name: str
    apply_url: str
    description_html: str = ""
    location: str | None = None
    country: str | None = None
    region_hint: list[str] | None = None  # structured place from the source (Adzuna "area")
    remote_hint: bool | None = None  # the source says remote/not remote explicitly
    workplace_hint: str | None = None  # e.g. Ashby "Hybrid"
    employment_type: str | None = None
    department: str | None = None
    posted_at: datetime | None = None
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    salary_currency: str | None = None
    salary_period: str | None = None


@dataclass(frozen=True, slots=True)
class BoardTarget:
    """One company board to read (ATS plugins); aggregators ignore this."""

    company_id: Any
    name: str
    board_token: str


@dataclass(slots=True)
class ScopeResult:
    """All postings for one scope (a board or an aggregator query), or why it failed.

    `complete=False` means the scope could not be fully read: its existing jobs are kept
    as they are instead of being marked stale.
    """

    scope: str
    postings: list[Posting] = field(default_factory=list)
    company_id: Any = None
    complete: bool = True
    error: str | None = None


@dataclass(frozen=True, slots=True)
class FetchContext:
    http: SourceHttpClient
    config: dict[str, Any]
    boards: list[BoardTarget]


class JobSourcePlugin(Protocol):
    key: str
    name: str
    uses_company_boards: bool  # ATS plugins read the admin-managed company list
    attribution: str | None  # shown next to jobs where the source's terms require it

    def is_configured(self, config: dict[str, Any]) -> str | None:
        """None if ready to run, otherwise a human-readable reason (e.g. missing API key)."""
        ...

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Return the cleaned config or raise ValueError with a message for the admin."""
        ...

    def config_options(self) -> dict[str, Any] | None:
        """Choices the admin UI can offer (e.g. supported countries), or None."""
        ...

    def fetch(self, ctx: FetchContext) -> AsyncIterator[ScopeResult]: ...
