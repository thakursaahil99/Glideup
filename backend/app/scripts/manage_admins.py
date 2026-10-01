"""Manage staff accounts from the command line.

    uv run python -m app.scripts.manage_admins grant you@example.com              # super_admin
    uv run python -m app.scripts.manage_admins grant ops@example.com --role support
    uv run python -m app.scripts.manage_admins revoke old-admin@example.com      # back to user
    uv run python -m app.scripts.manage_admins list

In Docker:  docker compose exec api python -m app.scripts.manage_admins list

The person then signs in normally (Google, or dev login locally); the account is matched by
email. All changes are audited with `source: cli`.
"""

import argparse
import asyncio
import sys

from app.core.errors import AppError
from app.core.rbac import Role
from app.db.session import dispose_engine, session_factory
from app.modules.admin import operator


async def _grant(email: str, role: Role, name: str | None) -> int:
    async with session_factory()() as session:
        user, created = await operator.set_role(session, email=email, role=role, name=name)
        await session.commit()
    verb = "Created" if created else "Updated"
    print(f"{verb} {user.email}: roles = {', '.join(user.role_names)}")
    if created:
        print("They can now sign in with this email (Google, or dev login locally).")
    return 0


async def _revoke(email: str) -> int:
    async with session_factory()() as session:
        user, _ = await operator.set_role(session, email=email, role=Role.USER, create=False)
        await session.commit()
    print(f"{user.email} is now a regular user.")
    return 0


async def _list() -> int:
    async with session_factory()() as session:
        rows = await operator.list_staff(session)
    if not rows:
        print("No staff accounts yet. Create one with: grant <email>")
        return 0
    print(f"{'email':<40}{'roles':<28}{'status':<12}signed in")
    for row in rows:
        print(
            f"{row.email:<40}{', '.join(row.roles):<28}{row.status:<12}"
            f"{'yes' if row.has_signed_in else 'not yet'}"
        )
    return 0


async def _main(args: argparse.Namespace) -> int:
    try:
        if args.command == "grant":
            return await _grant(args.email, Role(args.role), args.name)
        if args.command == "revoke":
            return await _revoke(args.email)
        return await _list()
    except AppError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(prog="manage_admins", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    grant = sub.add_parser("grant", help="create or update a staff account")
    grant.add_argument("email")
    grant.add_argument("--role", choices=[r.value for r in Role], default=Role.SUPER_ADMIN.value)
    grant.add_argument("--name", help="display name for a new account")
    revoke = sub.add_parser("revoke", help="turn a staff account back into a regular user")
    revoke.add_argument("email")
    sub.add_parser("list", help="list staff accounts")
    sys.exit(asyncio.run(_main(parser.parse_args())))


if __name__ == "__main__":
    main()
