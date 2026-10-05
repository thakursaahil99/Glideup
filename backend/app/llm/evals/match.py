"""Golden-example evals for match scoring.

    uv run python -m app.llm.evals.match                         # default embedding route
    uv run python -m app.llm.evals.match --route mock:mock-1     # skills/level only signal

Each case has a candidate and jobs graded by a human (3 strong, 2 good, 1 fair, 0 poor).
Everything goes through the production code path: the same embedding text recipe and
prefixes, and `score_match`. Reported per case:

- pairwise: share of job pairs with different grades that are ordered correctly;
- top-1: the best-graded job scores highest;
- bands: strong jobs score >= 65 and poor ones <= 35.

The raw cosine similarities are printed too: they are what `SEMANTIC_FLOOR` and
`SEMANTIC_CEILING` in `app.modules.matching.scoring` are calibrated against.
"""

import argparse
import asyncio
import json
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from app.core.config import get_settings, override_settings
from app.db.models import ExperienceLevel
from app.llm.factory import build_providers
from app.llm.gateway import LLMGateway
from app.llm.routing import Task
from app.modules.matching.embeddings import job_document_text, resume_query_text
from app.modules.matching.scoring import cosine, score_match
from app.modules.resumes.skills import canonicalize

GOLDEN = Path(__file__).with_name("match_ranking.json")
STRONG_AT_LEAST = 65
POOR_AT_MOST = 35


class _NullRecorder:
    async def record(self, usage: object) -> None:
        return None


@dataclass
class CaseResult:
    case: str
    rows: list[tuple[str, int, float, int]]  # job id, grade, cosine, score
    pairwise: float
    top1: bool
    bands: float


def evaluate(case: str, rows: list[tuple[str, int, float, int]]) -> CaseResult:
    pairs = [(a, b) for a, b in combinations(rows, 2) if a[1] != b[1]]
    correct = sum((a[3] > b[3]) == (a[1] > b[1]) and a[3] != b[3] for a, b in pairs)
    best = max(rows, key=lambda r: r[3])
    banded = [r for r in rows if r[1] in (0, 3)]
    in_band = sum(
        (r[3] >= STRONG_AT_LEAST) if r[1] == 3 else (r[3] <= POOR_AT_MOST) for r in banded
    )
    return CaseResult(
        case=case,
        rows=rows,
        pairwise=correct / len(pairs) if pairs else 1.0,
        top1=best[1] == max(r[1] for r in rows),
        bands=in_band / len(banded) if banded else 1.0,
    )


async def run(route: str | None) -> list[CaseResult]:
    settings = get_settings()
    if route:
        settings = settings.model_copy(
            update={"llm_routes": {Task.EMBEDDING: [route]}, "llm_allow_mock_fallback": False}
        )
        override_settings(settings)
    gateway = LLMGateway(settings, build_providers(settings), _NullRecorder())
    results = []
    for case in json.loads(GOLDEN.read_text(encoding="utf-8")):
        candidate = case["candidate"]
        jobs = case["jobs"]
        texts = [resume_query_text(candidate["resume"])] + [
            job_document_text(
                j["title"], "Example Co", ExperienceLevel(j["level"]), j["skills"], j["description"]
            )
            for j in jobs
        ]
        vectors = (await gateway.embed(texts)).vectors
        have = {canonicalize(s).normalized: canonicalize(s).name for s in candidate["skills"]}
        rows = []
        for job, vector in zip(jobs, vectors[1:], strict=True):
            similarity = cosine(vectors[0], vector)
            match = score_match(
                similarity=similarity,
                job_skills=job["skills"],
                have=have,
                level=ExperienceLevel(job["level"]),
                years=candidate["years"],
            )
            rows.append((job["id"], job["grade"], similarity, match.score if match else 0))
        results.append(evaluate(case["id"], rows))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", help="embedding provider:model, e.g. ollama:nomic-embed-text")
    args = parser.parse_args()
    results = asyncio.run(run(args.route))
    for r in results:
        top1 = "✓" if r.top1 else "✗"
        print(f"\n{r.case}  pairwise {r.pairwise:.2f}  top-1 {top1}  bands {r.bands:.2f}")
        for job_id, grade, similarity, score in sorted(r.rows, key=lambda x: -x[3]):
            print(f"  {job_id:<20} grade {grade}  cosine {similarity:.3f}  score {score:>3}")
    n = len(results)
    print(
        f"\nmean pairwise {sum(r.pairwise for r in results) / n:.2f} · "
        f"top-1 {sum(r.top1 for r in results)}/{n} · "
        f"bands {sum(r.bands for r in results) / n:.2f}"
    )


if __name__ == "__main__":
    main()
