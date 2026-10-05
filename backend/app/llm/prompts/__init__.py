"""Versioned prompt templates.

Prompts live in files named `<name>.<version>.<role>.j2` next to this module — never as
inline strings in code. `ACTIVE_VERSIONS` picks the version in use; every LLM call records
`<name>@<version>` in `llm_usage`, so output quality can be traced to the exact prompt.
Phase 5 moves the active version (and editing, diff and rollback) into the admin console.
"""

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.llm.types import Message, Role

PROMPT_DIR = Path(__file__).parent
ACTIVE_VERSIONS: dict[str, str] = {
    "resume_parse": "v2",
    "portfolio_parse": "v1",
    "skill_gap": "v1",
    "interview_plan": "v1",
    "interviewer": "v1",
    "interview_hint": "v1",
    "interview_report": "v1",
    "question_generate": "v1",
}
_ROLES: tuple[Role, ...] = ("system", "user")


@lru_cache(maxsize=1)
def _environment() -> Environment:
    # Plain-text prompts: autoescape would corrupt them. Untrusted input is fenced by the
    # templates themselves (see `fence`), not HTML-escaped.
    return Environment(  # noqa: S701
        loader=FileSystemLoader(PROMPT_DIR),
        undefined=StrictUndefined,
        keep_trailing_newline=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def fence(text: str, tag: str) -> str:
    """Wrap untrusted content (resumes, job descriptions) in tags it cannot close itself."""
    cleaned = text.replace(f"</{tag}>", f"</ {tag}>").replace(f"<{tag}>", f"< {tag}>")
    return f"<{tag}>\n{cleaned}\n</{tag}>"


def render(name: str, version: str | None = None, **context: object) -> tuple[list[Message], str]:
    version = version or ACTIVE_VERSIONS[name]
    env = _environment()
    messages: list[Message] = []
    for role in _ROLES:
        filename = f"{name}.{version}.{role}.j2"
        if (PROMPT_DIR / filename).exists():
            content = env.get_template(filename).render(fence=fence, **context).strip()
            messages.append(Message(role=role, content=content))
    if not messages:
        raise FileNotFoundError(f"No prompt templates found for {name}@{version}")
    return messages, f"{name}@{version}"
