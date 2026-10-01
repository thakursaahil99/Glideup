"""Golden-example evals for resume parsing.

    uv run python -m app.llm.evals.run                       # default route (as configured)
    uv run python -m app.llm.evals.run --route ollama:qwen2.5:3b
    uv run python -m app.llm.evals.run --route mock:mock-1

Scores each example on: name, years-in-range, skill recall/precision, companies and
education found. Use it to compare models and prompt versions before switching.
"""

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from app.core.config import get_settings, override_settings
from app.db.models import LLMUsage
from app.llm import prompts
from app.llm.factory import build_providers
from app.llm.gateway import LLMGateway
from app.llm.routing import Task
from app.llm.types import AllProvidersFailedError
from app.modules.resumes import heuristics  # noqa: F401  (mock parser)
from app.modules.resumes.grounding import ground
from app.modules.resumes.schemas import ParsedResume
from app.modules.resumes.skills import canonicalize

GOLDEN = Path(__file__).with_name("resume_parse.json")


class _NullRecorder:
    async def record(self, usage: LLMUsage) -> None:
        return None


@dataclass
class Score:
    example: str
    name_ok: bool
    years_ok: bool
    skill_recall: float
    skill_precision: float
    companies_found: float
    education_found: float
    seconds: float
    error: str | None = None

    @property
    def overall(self) -> float:
        if self.error:
            return 0.0
        parts = [
            float(self.name_ok),
            float(self.years_ok),
            self.skill_recall,
            self.skill_precision,
            self.companies_found,
            self.education_found,
        ]
        return sum(parts) / len(parts)


def _contains_all(expected: list[str], found: list[str]) -> float:
    if not expected:
        return 1.0
    haystack = " | ".join(found).lower()
    return sum(e.lower() in haystack for e in expected) / len(expected)


class Expected(BaseModel):
    full_name: str
    total_years_experience: tuple[float, float]
    skills: list[str]
    companies: list[str]
    education_institutions: list[str]


def score(example_id: str, expected: Expected, parsed: ParsedResume, secs: float) -> Score:
    want = {canonicalize(s).normalized for s in expected.skills}
    got = {canonicalize(s.name).normalized for s in parsed.skills}
    low, high = expected.total_years_experience
    years = parsed.total_years_experience
    return Score(
        example=example_id,
        name_ok=(parsed.full_name or "").lower() == expected.full_name.lower(),
        years_ok=years is not None and low <= years <= high,
        skill_recall=len(want & got) / len(want) if want else 1.0,
        skill_precision=len(want & got) / len(got) if got else 0.0,
        companies_found=_contains_all(expected.companies, [e.company for e in parsed.experience]),
        education_found=_contains_all(
            expected.education_institutions, [e.institution for e in parsed.education]
        ),
        seconds=secs,
    )


async def run(route: str | None) -> list[Score]:
    settings = get_settings()
    if route:
        settings = settings.model_copy(
            update={"llm_routes": {Task.RESUME_PARSE: [route]}, "llm_allow_mock_fallback": False}
        )
        override_settings(settings)
    gateway = LLMGateway(settings, build_providers(settings), _NullRecorder())
    scores = []
    for example in json.loads(GOLDEN.read_text(encoding="utf-8")):
        messages, _ = prompts.render(
            "resume_parse", resume_text=example["resume"], today=date.today().isoformat()
        )
        started = time.perf_counter()
        try:
            parsed, _ = await gateway.complete_json(Task.RESUME_PARSE, messages, ParsedResume)
        except AllProvidersFailedError as exc:
            scores.append(Score(example["id"], False, False, 0, 0, 0, 0, 0, error=str(exc)))
            continue
        parsed = ground(parsed, example["resume"])  # same post-processing as production
        scores.append(
            score(
                example["id"],
                Expected.model_validate(example["expected"]),
                parsed,
                time.perf_counter() - started,
            )
        )
    return scores


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", help="provider:model to evaluate, e.g. ollama:qwen2.5:3b")
    args = parser.parse_args()
    scores = asyncio.run(run(args.route))
    columns = [("example", -18), ("name", 6), ("years", 7), ("recall", 8), ("prec.", 7)]
    columns += [("cos", 6), ("edu", 6), ("secs", 7), ("score", 7)]
    header = "".join(f"{n:<{-w}}" if w < 0 else f"{n:>{w}}" for n, w in columns)
    print(header)
    for s in scores:
        if s.error:
            print(f"{s.example:<18}  ERROR {s.error[:90]}")
            continue
        print(
            f"{s.example:<18}{'✓' if s.name_ok else '✗':>6}{'✓' if s.years_ok else '✗':>7}"
            f"{s.skill_recall:>8.2f}{s.skill_precision:>7.2f}{s.companies_found:>6.2f}"
            f"{s.education_found:>6.2f}{s.seconds:>7.1f}{s.overall:>7.2f}"
        )
    mean = sum(s.overall for s in scores) / len(scores)
    print(f"\nmean score: {mean:.2f}")


if __name__ == "__main__":
    main()
