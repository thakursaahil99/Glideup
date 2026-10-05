"""Install the six language runtimes into the Piston sandbox (run once after first start).

    uv run python -m app.scripts.install_sandbox_runtimes
    docker compose exec api python -m app.scripts.install_sandbox_runtimes

Picks the newest available version of each runtime. Safe to re-run.
"""

import asyncio

import httpx

from app.core.config import get_settings
from app.modules.coding.runner import PISTON_LANGUAGES

# Piston package names differ from language names for a few runtimes.
PACKAGES = {"python": "python", "javascript": "node", "typescript": "typescript",
            "java": "java", "cpp": "gcc", "go": "go"}  # fmt: skip


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) if p.isdigit() else 0 for p in version.split("."))


async def main() -> None:
    base = get_settings().piston_url.rstrip("/")
    async with httpx.AsyncClient(timeout=600) as client:
        available = (await client.get(f"{base}/api/v2/packages")).json()
        for key, package in PACKAGES.items():
            versions = [p for p in available if p["language"] == package]
            if not versions:
                print(f"{key}: no '{package}' package available")
                continue
            best = max(versions, key=lambda p: _version_key(p["language_version"]))
            if best.get("installed"):
                print(f"{key}: {package} {best['language_version']} already installed")
                continue
            print(f"{key}: installing {package} {best['language_version']} ...", flush=True)
            response = await client.post(
                f"{base}/api/v2/packages",
                json={"language": package, "version": best["language_version"]},
            )
            print(f"  -> {response.status_code}")
        runtimes = (await client.get(f"{base}/api/v2/runtimes")).json()
        names = {r["language"] for r in runtimes} | {
            a for r in runtimes for a in r.get("aliases", [])
        }
        missing = [k for k, (lang, _) in PISTON_LANGUAGES.items() if lang not in names]
        print("ready" if not missing else f"still missing: {', '.join(missing)}")


if __name__ == "__main__":
    asyncio.run(main())
