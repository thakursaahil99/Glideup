"""Read a GitHub profile through the public REST API (no scraping, no LLM).

Two requests per analysis: the user and their most recently pushed repositories.
Unauthenticated calls are limited to 60/hour per IP; set GITHUB_API_TOKEN for 5,000/hour.
Facts come straight from GitHub, so nothing here needs grounding.
"""

import re
from collections import Counter
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings
from app.core.safe_fetch import FetchError
from app.modules.portfolio.schemas import PortfolioResult, PortfolioSkill, Project
from app.modules.resumes.skills import canonicalize, detect_skills

API = "https://api.github.com"
_USERNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
# github.com/<these> are GitHub's own pages, not users.
_RESERVED = {
    "about",
    "features",
    "orgs",
    "settings",
    "topics",
    "trending",
    "marketplace",
    "sponsors",
}
# Languages GitHub reports that say little about someone's skills.
_IGNORED_LANGUAGES = {"Jupyter Notebook", "Makefile", "Batchfile", "Procfile", "Roff"}
MAX_PROJECTS = 6


def username_from_url(url: str) -> str:
    """https://github.com/octocat/hello-world -> "octocat"."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    segments = [s for s in parts.path.split("/") if s]
    if host != "github.com" or not segments:
        raise ValueError("Enter your GitHub profile link, e.g. https://github.com/yourname")
    username = segments[0]
    if username.lower() in _RESERVED or not _USERNAME.match(username):
        raise ValueError("Enter your GitHub profile link, e.g. https://github.com/yourname")
    return username


async def _get(client: httpx.AsyncClient, path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        response = await client.get(f"{API}{path}", params=params)
    except httpx.HTTPError as exc:
        raise FetchError("We couldn't reach GitHub. Please try again in a few minutes.") from exc
    if response.status_code == 404:
        raise FetchError("We couldn't find that GitHub user. Check the link.")
    if response.status_code in (403, 429):
        raise FetchError("GitHub's rate limit was reached. Please try again in an hour.")
    if response.status_code != 200:
        raise FetchError(f"GitHub answered with HTTP {response.status_code}.")
    return response.json()


async def analyze_github(
    url: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> tuple[PortfolioResult, str | None]:
    """Return the analysis and the user's own website (GitHub's "blog" field), if any."""
    username = username_from_url(url)
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "GlideUp-portfolio-analyzer",
    }
    token = get_settings().github_api_token
    if token:
        headers["Authorization"] = f"Bearer {token.get_secret_value()}"
    async with httpx.AsyncClient(transport=transport, headers=headers, timeout=15.0) as client:
        user = await _get(client, f"/users/{username}")
        repos = await _get(
            client,
            f"/users/{username}/repos",
            {"per_page": 100, "sort": "pushed", "type": "owner"},
        )
    return summarize(user, repos), (user.get("blog") or None)


def summarize(user: dict[str, Any], repos: list[dict[str, Any]]) -> PortfolioResult:
    own = [r for r in repos if not r.get("fork") and not r.get("archived")]

    languages = Counter(
        r["language"] for r in own if r.get("language") and r["language"] not in _IGNORED_LANGUAGES
    )
    skills: list[PortfolioSkill] = []
    for language, count in languages.most_common():
        canonical = canonicalize(language)
        noun = "repository" if count == 1 else "repositories"
        skills.append(
            PortfolioSkill.model_validate(
                {
                    "name": canonical.name,
                    "category": canonical.category or "language",
                    "evidence": f"Main language of {count} {noun}",
                }
            )
        )

    # Frameworks and tools: from repo topics and descriptions, counted per repository.
    mentioned: Counter[str] = Counter()
    categories: dict[str, str] = {}
    for repo in own:
        text = " ".join([*(repo.get("topics") or []), repo.get("description") or ""])
        for name, category in detect_skills(text):
            mentioned[name] += 1
            categories[name] = category
    for name, count in mentioned.most_common():
        noun = "repository" if count == 1 else "repositories"
        skills.append(
            PortfolioSkill.model_validate(
                {"name": name, "category": categories[name], "evidence": f"Used in {count} {noun}"}
            )
        )

    # Most-starred first; ties keep GitHub's most-recently-pushed order (sort is stable).
    ranked = sorted(own, key=lambda r: r.get("stargazers_count") or 0, reverse=True)
    projects = []
    for repo in ranked[:MAX_PROJECTS]:
        text = " ".join([*(repo.get("topics") or []), repo.get("description") or ""])
        tech = [repo["language"]] if repo.get("language") else []
        tech += [name for name, _ in detect_skills(text) if name not in tech]
        projects.append(
            Project(
                name=repo["name"],
                description=(repo.get("description") or "")[:500] or None,
                url=repo.get("html_url"),
                technologies=tech[:15],
                stars=repo.get("stargazers_count") or 0,
            )
        )

    bio = (user.get("bio") or "").strip()
    return PortfolioResult(
        headline=bio[:200] or None,
        skills=skills,
        projects=projects,
        languages=dict(languages.most_common()),
        stats={
            "public_repos": int(user.get("public_repos") or 0),
            "original_repos": len(own),
            "followers": int(user.get("followers") or 0),
            "total_stars": sum(int(r.get("stargazers_count") or 0) for r in own),
        },
    )
