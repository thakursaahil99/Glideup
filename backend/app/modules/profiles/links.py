"""Profile links (portfolio, LinkedIn, GitHub): normalization and classification.

Links are rendered as <a href>, so only plain http(s) URLs with a real hostname are kept.
"""

import re
from urllib.parse import urlsplit

_URL = re.compile(r"^https?://[\w-]+(\.[\w-]+)*\.[a-z]{2,}(:\d+)?(/\S*)?$", re.IGNORECASE)


def normalize_url(value: str | None) -> str | None:
    """Adds https:// when missing; blank -> None; anything not a web address -> ValueError."""
    if value is None or not value.strip():
        return None
    url = value.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.IGNORECASE):
        url = f"https://{url}"
    if len(url) > 300 or not _URL.match(url):
        raise ValueError("Enter a valid web address, e.g. https://example.com")
    return url


def host_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def is_linkedin(url: str) -> bool:
    host = host_of(url)
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def is_github(url: str) -> bool:
    return host_of(url) == "github.com"


def classify(links: list[str]) -> dict[str, str]:
    """Pick at most one portfolio, LinkedIn and GitHub link from a resume's link list."""
    found: dict[str, str] = {}
    for link in links:
        try:
            url = normalize_url(link)
        except ValueError:
            continue
        if url is None:
            continue
        if is_linkedin(url):
            kind = "linkedin_url"
        elif is_github(url):
            kind = "github_url"
        else:
            kind = "portfolio_url"
        found.setdefault(kind, url)
    return found
