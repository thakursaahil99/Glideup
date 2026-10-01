"""Idempotent reference-data seed: job sources and the verified company list.

    uv run python -m app.scripts.seed

Runs after migrations in Docker Compose. Safe to run any number of times; it never
overwrites settings an admin changed.
"""

import asyncio

from app.db.session import dispose_engine, session_factory
from app.modules.jobs.catalog import seed


async def main() -> None:
    async with session_factory()() as session:
        result = await seed(session)
        await session.commit()
    await dispose_engine()
    print(
        f"companies: {result.created} created, {result.updated} updated, {result.skipped} unchanged"
    )


if __name__ == "__main__":
    asyncio.run(main())
