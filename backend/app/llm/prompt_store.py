"""Prompt templates managed from the admin console.

Every LLM call renders its prompt through `render()`, which uses the template's *active*
version from the database. The `.j2` files next to `app/llm/prompts` are the seed: they
are imported as versions 1, 2, ... (`ensure_imported`) and are used directly whenever the
database has no row for a template (tests, a fresh install, the eval runner).

Admin-written templates are untrusted text that will be executed, so they render in
Jinja's sandbox and may only use the variables the code passes for that template.
"""

import time
from dataclasses import dataclass

import structlog
from jinja2 import StrictUndefined, TemplateSyntaxError, meta
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PromptTemplate, PromptTemplateVersion
from app.db.session import session_factory
from app.llm import prompts
from app.llm.types import Message

logger = structlog.get_logger(__name__)

CACHE_TTL_S = 30.0  # other processes pick up an activation within this time

DESCRIPTIONS: dict[str, str] = {
    "resume_parse": "Extracts structured data (skills, experience, education) from a resume.",
    "portfolio_parse": "Reads skills and projects from a personal portfolio website.",
    "skill_gap": "Explains a candidate's gaps for one job, with ways to close them.",
    "interview_plan": "Writes the questions for a job-specific mock interview.",
    "interviewer": "The interviewer's replies: follow-ups, and when to move on.",
    "interview_hint": "A small hint when the candidate asks for one.",
    "interview_report": "Scores a finished interview against its rubric.",
    "question_generate": "Writes a coding problem, test inputs and a reference solution.",
}

_sandbox = SandboxedEnvironment(
    undefined=StrictUndefined, keep_trailing_newline=False, trim_blocks=True, lstrip_blocks=True
)


@dataclass(frozen=True, slots=True)
class ActivePrompt:
    label: str  # "interviewer@v3"
    system: str
    user: str


_cache: dict[str, tuple[float, ActivePrompt | None]] = {}


def invalidate(name: str | None = None) -> None:
    if name is None:
        _cache.clear()
    else:
        _cache.pop(name, None)


def file_versions(name: str) -> dict[int, tuple[str, str]]:
    """{version number: (system, user)} for the template files of `name`."""
    found: dict[int, tuple[str, str]] = {}
    for path in prompts.PROMPT_DIR.glob(f"{name}.v*.system.j2"):
        label = path.name.removeprefix(f"{name}.").split(".")[0]  # "v2"
        if not label[1:].isdigit():
            continue
        user = prompts.PROMPT_DIR / f"{name}.{label}.user.j2"
        found[int(label[1:])] = (
            path.read_text(encoding="utf-8"),
            user.read_text(encoding="utf-8") if user.exists() else "",
        )
    return found


def template_names() -> list[str]:
    return sorted(prompts.ACTIVE_VERSIONS)


def allowed_variables(name: str) -> set[str]:
    """Variables the code passes to this template: those its shipped versions use."""
    names: set[str] = set()
    for system, user in file_versions(name).values():
        for source in (system, user):
            names |= meta.find_undeclared_variables(_sandbox.parse(source))
    return names


def validate(name: str, system: str, user: str) -> list[str]:
    """Problems that would break rendering. Empty list = OK to save."""
    if name not in prompts.ACTIVE_VERSIONS:
        return [f"Unknown template '{name}'"]
    if not system.strip():
        return ["The system prompt can't be empty."]
    allowed = allowed_variables(name)
    problems: list[str] = []
    for part, source in (("system", system), ("user", user)):
        try:
            used = meta.find_undeclared_variables(_sandbox.parse(source))
        except TemplateSyntaxError as exc:
            problems.append(f"{part}: syntax error on line {exc.lineno}: {exc.message}")
            continue
        unknown = sorted(used - allowed)
        if unknown:
            problems.append(
                f"{part}: unknown variable(s) {', '.join(unknown)}; "
                f"available: {', '.join(sorted(allowed - {'fence'}))}"
            )
    return problems


def render_text(system: str, user: str, **context: object) -> list[Message]:
    messages: list[Message] = []
    for role, source in (("system", system), ("user", user)):
        if source.strip():
            text = _sandbox.from_string(source).render(fence=prompts.fence, **context).strip()
            messages.append(Message(role=role, content=text))  # type: ignore[arg-type]
    return messages


async def _load_active(name: str) -> ActivePrompt | None:
    async with session_factory()() as session:
        row = await session.execute(
            select(PromptTemplateVersion)
            .join(PromptTemplate, PromptTemplate.name == PromptTemplateVersion.template_name)
            .where(
                PromptTemplate.name == name,
                PromptTemplateVersion.version == PromptTemplate.active_version,
            )
        )
        version = row.scalar_one_or_none()
    if version is None:
        return None
    return ActivePrompt(f"{name}@v{version.version}", version.system, version.user)


async def _active(name: str) -> ActivePrompt | None:
    now = time.monotonic()
    cached = _cache.get(name)
    if cached is None or cached[0] < now:
        try:
            active = await _load_active(name)
        except Exception:  # the database is optional for prompts; files always work
            logger.warning("prompt_store_unavailable", name=name, exc_info=True)
            active = None
        _cache[name] = (now + CACHE_TTL_S, active)
        cached = _cache[name]
    return cached[1]


async def active_label(name: str) -> str:
    """ "name@vN" of the version calls use right now (stored with results for staleness)."""
    active = await _active(name)
    return active.label if active else f"{name}@{prompts.ACTIVE_VERSIONS[name]}"


async def render(name: str, **context: object) -> tuple[list[Message], str]:
    """Render the active version of a prompt. Returns (messages, "name@vN")."""
    active = await _active(name)
    if active is None:
        return prompts.render(name, None, **context)
    return render_text(active.system, active.user, **context), active.label


async def ensure_imported(session: AsyncSession) -> None:
    """Import shipped template files as versions (idempotent). A template that is new to
    the database gets the version the code currently selects as active."""
    templates = {t.name: t for t in await session.scalars(select(PromptTemplate))}
    existing = {
        (v.template_name, v.version) for v in await session.scalars(select(PromptTemplateVersion))
    }
    for name in template_names():
        template = templates.get(name)
        if template is None:
            template = PromptTemplate(name=name, description=DESCRIPTIONS.get(name, ""))
            session.add(template)
            await session.flush()
        for number, (system, user) in sorted(file_versions(name).items()):
            if (name, number) not in existing:
                session.add(
                    PromptTemplateVersion(
                        template_name=name,
                        version=number,
                        system=system,
                        user=user,
                        notes="Shipped with the code",
                        source="file",
                    )
                )
        if template.active_version is None:
            template.active_version = int(prompts.ACTIVE_VERSIONS[name].removeprefix("v"))
    await session.flush()
