"""Match score: how well a candidate fits a job, from 0 to 100.

Fit is a weighted average of the signals that are available, each scaled to 0..1:

- **semantic** (weight 0.60): cosine similarity of the resume and job embeddings, rescaled
  from the range real pairs actually fall in (see `SEMANTIC_FLOOR`/`SEMANTIC_CEILING`).
  Captures role, domain and seniority language that a skill list misses.
- **skills** (weight 0.40): share of the job's detected skills the candidate has
  (resume or portfolio). A closely related skill (MySQL for PostgreSQL) counts half.
  The weight shrinks for jobs that mention only one or two skills, where coverage is noise.

**Level** then scales the result: years of experience against the band the job's level
implies. It can only lower a score (down to `LEVEL_FLOOR` of it), never raise one, because
"your years suit a senior role" says nothing about whether it is the *right* senior role.

A signal that is unknown is left out rather than guessed. Without embeddings the score is
still given from skills (and level) and flagged `partial`. Everything here is pure and
deterministic so it can be unit-tested and evaluated against golden examples
(`python -m app.llm.evals.match`).
"""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.db.models import ExperienceLevel
from app.modules.resumes.skills import canonicalize

W_SEMANTIC = 0.60
W_SKILLS = 0.40
LEVEL_FLOOR = 0.70  # a complete level mismatch keeps 70% of the fit score
FULL_SKILL_WEIGHT_AT = 3  # jobs listing fewer skills get a proportionally smaller weight

# Calibrated on real data (nomic-embed-text with search_query/search_document prefixes, a
# real full-stack resume against 3,456 live jobs): unrelated roles (recruiting, sales)
# score 0.49-0.57, the median job 0.65, the best-fitting roles 0.78-0.80.
SEMANTIC_FLOOR = 0.58
SEMANTIC_CEILING = 0.78

# Years of experience each level usually asks for: (min, max).
LEVEL_YEARS: dict[ExperienceLevel, tuple[float, float]] = {
    ExperienceLevel.INTERNSHIP: (0, 1),
    ExperienceLevel.ENTRY: (0, 2),
    ExperienceLevel.MID: (2, 5),
    ExperienceLevel.SENIOR: (5, 10),
    ExperienceLevel.STAFF: (8, 30),
    ExperienceLevel.MANAGER: (6, 30),
}
UNDER_PENALTY_PER_YEAR = 0.25  # 4 years short of the band -> no level credit
OVER_PENALTY_PER_YEAR = 0.10  # over-qualified is a milder mismatch...
OVER_FLOOR = 0.4  # ...and never drops below this

# Skills close enough that knowing one makes the other quick to pick up.
RELATED_GROUPS: tuple[frozenset[str], ...] = tuple(
    frozenset(canonicalize(s).normalized for s in group)
    for group in (
        ("PostgreSQL", "MySQL", "SQL Server", "Oracle", "SQLite"),
        ("MongoDB", "DynamoDB", "Cassandra", "Cosmos DB"),
        ("AWS", "Azure", "GCP"),
        ("React", "Angular", "Vue.js", "Svelte"),
        ("Next.js", "React"),
        ("Django", "Flask", "FastAPI"),
        ("Express", "NestJS", "Node.js"),
        ("Spring Boot", "Java"),
        ("Kotlin", "Java"),
        ("JavaScript", "TypeScript"),
        ("GitHub Actions", "Jenkins", "Azure DevOps", "CI/CD"),
        ("Kafka", "RabbitMQ"),
        ("Playwright", "Cypress", "Selenium"),
        ("Jest", "Pytest", "Unit Testing"),
        ("PyTorch", "TensorFlow"),
        ("Docker", "Kubernetes"),
        ("Terraform", "Ansible", "Helm"),
        ("React Native", "Flutter"),
        ("C#", ".NET"),
    )
)


@dataclass(frozen=True, slots=True)
class Transferable:
    skill: str  # what the job asks for
    via: str  # what the candidate has


@dataclass(frozen=True, slots=True)
class MatchResult:
    score: int
    semantic: float | None
    skills: float | None
    level: float | None
    matched: list[str] = field(default_factory=list)
    transferable: list[Transferable] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def partial(self) -> bool:
        """Scored without the semantic signal (embeddings not ready)."""
        return self.semantic is None

    @property
    def label(self) -> str:
        return match_label(self.score)


def match_label(score: int) -> str:
    if score >= 75:
        return "Strong match"
    if score >= 55:
        return "Good match"
    if score >= 35:
        return "Fair match"
    return "Low match"


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def semantic_score(similarity: float) -> float:
    settings = get_settings()
    floor = settings.match_semantic_floor
    if floor is None:
        floor = SEMANTIC_FLOOR
    ceiling = settings.match_semantic_ceiling or SEMANTIC_CEILING
    scaled = (similarity - floor) / (ceiling - floor)
    return min(1.0, max(0.0, scaled))


def level_fit(level: ExperienceLevel, years: float | None) -> float | None:
    band = LEVEL_YEARS.get(level)
    if band is None or years is None:
        return None
    low, high = band
    if years < low:
        return max(0.0, 1 - (low - years) * UNDER_PENALTY_PER_YEAR)
    if years > high:
        return max(OVER_FLOOR, 1 - (years - high) * OVER_PENALTY_PER_YEAR)
    return 1.0


def skill_overlap(
    job_skills: Iterable[str], have: Mapping[str, str]
) -> tuple[list[str], list[Transferable], list[str]]:
    """Split the job's skills into matched / transferable / missing.

    `have` maps normalised skill key -> display name for everything the candidate has.
    """
    matched: list[str] = []
    transferable: list[Transferable] = []
    missing: list[str] = []
    seen: set[str] = set()
    for raw in job_skills:
        skill = canonicalize(raw)
        if skill.normalized in seen:  # "Postgres" and "PostgreSQL" are one skill
            continue
        seen.add(skill.normalized)
        if skill.normalized in have:
            matched.append(skill.name)
            continue
        via = next(
            (
                have[other]
                for group in RELATED_GROUPS
                if skill.normalized in group
                for other in sorted(group)
                if other in have
            ),
            None,
        )
        if via:
            transferable.append(Transferable(skill.name, via))
        else:
            missing.append(skill.name)
    return matched, transferable, missing


def score_match(
    *,
    similarity: float | None,
    job_skills: Sequence[str],
    have: Mapping[str, str],
    level: ExperienceLevel,
    years: float | None,
) -> MatchResult | None:
    """Combine the available signals. None when there is nothing to judge fit on."""
    matched, transferable, missing = skill_overlap(job_skills, have)
    total = len(matched) + len(transferable) + len(missing)

    parts: list[tuple[float, float]] = []  # (value, weight)
    semantic = semantic_score(similarity) if similarity is not None else None
    if semantic is not None:
        parts.append((semantic, W_SEMANTIC))
    coverage = (len(matched) + 0.5 * len(transferable)) / total if total else None
    if coverage is not None:
        parts.append((coverage, W_SKILLS * min(1.0, total / FULL_SKILL_WEIGHT_AT)))
    if not parts:
        return None
    fit = level_fit(level, years)

    value = sum(v * w for v, w in parts) / sum(w for _, w in parts)
    if fit is not None:
        value *= LEVEL_FLOOR + (1 - LEVEL_FLOOR) * fit
    return MatchResult(
        score=round(value * 100),
        semantic=semantic,
        skills=coverage,
        level=fit,
        matched=matched,
        transferable=transferable,
        missing=missing,
    )
