"""Sources and companies: seeding, CSV import and admin edits."""

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ATS, Company, JobSource
from app.jobsources.registry import DISABLED_BY_DEFAULT, PLUGINS

SEED_COMPANIES = Path(__file__).resolve().parents[2] / "jobsources" / "seed" / "companies.csv"
_TOKEN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:100] or "company"


async def ensure_sources(session: AsyncSession) -> list[JobSource]:
    """One row per installed plugin. Existing admin settings are never overwritten."""
    existing = {s.key: s for s in await session.scalars(select(JobSource))}
    for key, plugin in PLUGINS.items():
        if key not in existing:
            source = JobSource(
                key=key,
                name=plugin.name,
                enabled=key not in DISABLED_BY_DEFAULT,
                schedule_minutes=360,
                rate_limit_per_minute=30 if key == "adzuna" else 60,
                config={},
            )
            session.add(source)
            existing[key] = source
    await session.flush()
    return list(existing.values())


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def parse_company_csv(text: str) -> list[dict[str, str]]:
    lines = [
        line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]
    return [
        {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        for row in csv.DictReader(io.StringIO("\n".join(lines)))
    ]


async def import_companies(session: AsyncSession, rows: list[dict[str, str]]) -> ImportResult:
    """Upsert companies by (ats, board_token). Bad rows are reported, not fatal."""
    result = ImportResult()
    for number, row in enumerate(rows, start=2):  # row 1 is the header
        name, ats, token = (
            row.get("name", ""),
            row.get("ats", "").lower(),
            row.get("board_token", ""),
        )
        if not name or ats not in ATS._value2member_map_ or not _TOKEN.match(token):
            result.errors.append(
                f"row {number}: need name, ats (greenhouse|lever|ashby), board_token"
            )
            result.skipped += 1
            continue
        company = await session.scalar(
            select(Company).where(Company.ats == ATS(ats), Company.board_token == token)
        )
        if company is None:
            slug = slugify(name)
            if await session.scalar(select(Company.id).where(Company.slug == slug)):
                slug = f"{slug}-{ats}"
            session.add(
                Company(
                    name=name[:200],
                    slug=slug,
                    ats=ATS(ats),
                    board_token=token,
                    website=row.get("website") or None,
                )
            )
            result.created += 1
        elif company.name != name:
            company.name = name[:200]
            result.updated += 1
        else:
            result.skipped += 1
        await session.flush()
    return result


async def seed(session: AsyncSession) -> ImportResult:
    await ensure_sources(session)
    return await import_companies(session, parse_company_csv(SEED_COMPANIES.read_text("utf-8")))
