"""Portfolio websites: fetch (SSRF-safe), extract visible text, LLM-parse, ground.

Sites rendered entirely in the browser (React/Wix with no server-side HTML) have almost
no text in the HTML we receive; those fail with a clear message instead of a guess.
"""

import json
import re
from html.parser import HTMLParser

from app.llm.factory import MOCK_HANDLERS
from app.llm.routing import Task
from app.llm.types import CompletionRequest
from app.modules.portfolio.schemas import ParsedPortfolio, PortfolioResult, PortfolioSkill
from app.modules.resumes.skills import canonicalize, detect_skills

MIN_TEXT_CHARS = 150
MAX_TEXT_CHARS = 15_000
_SKIPPED_TAGS = {"script", "style", "noscript", "svg", "template", "iframe", "head"}
_BLOCK_TAGS = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "section", "tr"}
_SITE_BLOCK = re.compile(r"<website>\n?(.*?)\n?</website>", re.S)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self.description = ""
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            values = dict(attrs)
            if (values.get("name") or values.get("property") or "").lower() in (
                "description",
                "og:description",
            ):
                self.description = self.description or (values.get("content") or "")
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in _SKIPPED_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip_depth:
            self.parts.append(data)


def visible_text(html: str) -> str:
    """Title, meta description and the readable text of a page, whitespace-normalised."""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    body = "\n".join(line for line in lines if line)
    header = "\n".join(p for p in (parser.title.strip(), parser.description.strip()) if p)
    return f"{header}\n{body}".strip()[:MAX_TEXT_CHARS]


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", text.lower()).split())


def ground(parsed: ParsedPortfolio, source: str) -> ParsedPortfolio:
    """Keep only skills and projects the page actually mentions (hallucination, injection)."""
    haystack = _norm(source)
    detected = {name for name, _ in detect_skills(source)}

    def mentioned(value: str) -> bool:
        return bool(_norm(value)) and f" {_norm(value)} " in f" {haystack} "

    skills = [
        s for s in parsed.skills if canonicalize(s.name).name in detected or mentioned(s.name)
    ]
    projects = [p for p in parsed.projects if mentioned(p.name)]
    return parsed.model_copy(update={"skills": skills, "projects": projects})


def to_result(parsed: ParsedPortfolio) -> PortfolioResult:
    return PortfolioResult(
        headline=parsed.headline,
        summary=parsed.summary,
        skills=[
            PortfolioSkill.model_validate(
                {
                    "name": s.name,
                    "category": s.category,
                    "evidence": "Mentioned on your portfolio site",
                }
            )
            for s in parsed.skills
        ],
        projects=parsed.projects,
    )


# ------------------------------------------------------------------ offline fallback


def parse_portfolio_text(text: str) -> dict[str, object]:
    """Heuristic parse used by the mock provider: known skills, title as headline."""
    first_line = text.splitlines()[0] if text else ""
    return {
        "headline": first_line[:200] or None,
        "summary": None,
        "skills": [{"name": name, "category": category} for name, category in detect_skills(text)],
        "projects": [],
    }


def _mock_portfolio_parse(request: CompletionRequest) -> str:
    prompt = "\n".join(m.content for m in request.messages if m.role == "user")
    match = _SITE_BLOCK.search(prompt)
    return json.dumps(parse_portfolio_text(match.group(1) if match else prompt))


MOCK_HANDLERS[Task.PORTFOLIO_PARSE] = _mock_portfolio_parse
