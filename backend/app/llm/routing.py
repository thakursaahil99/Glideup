"""Which provider/model serves which task, in fallback order.

Cheap/local first for high-volume extraction; stronger hosted models as fallback (and,
later, first for interviews and reports). Unconfigured providers are skipped, so the
same table works on a laptop with only Ollama and in the cloud with Azure OpenAI.
"""

from dataclasses import dataclass

from app.core.config import Settings


class Task:
    RESUME_PARSE = "resume_parse"
    PORTFOLIO_PARSE = "portfolio_parse"
    SKILL_GAP = "skill_gap"
    INTERVIEW_PLAN = "interview_plan"
    INTERVIEWER = "interviewer"
    INTERVIEW_HINT = "interview_hint"
    INTERVIEW_REPORT = "interview_report"
    QUESTION_GENERATE = "question_generate"
    FRAMEWORK_GRADE = "framework_grade"
    EMBEDDING = "embedding"


_HOSTED_FIRST = [
    "github:openai/gpt-4.1-mini",
    "ollama:qwen2.5:3b",
    "openrouter:meta-llama/llama-3.3-70b-instruct:free",
]

DEFAULT_ROUTES: dict[str, list[str]] = {
    Task.RESUME_PARSE: [
        "ollama:qwen2.5:3b",
        "github:openai/gpt-4.1-mini",
        "openrouter:meta-llama/llama-3.3-70b-instruct:free",
    ],
    # Same shape of work as resume parsing (structured extraction), so the same chain.
    Task.PORTFOLIO_PARSE: [
        "ollama:qwen2.5:3b",
        "github:openai/gpt-4.1-mini",
        "openrouter:meta-llama/llama-3.3-70b-instruct:free",
    ],
    # Reasoning over two documents; small local model first, hosted ones as fallback.
    Task.SKILL_GAP: [
        "ollama:qwen2.5:3b",
        "github:openai/gpt-4.1-mini",
        "openrouter:meta-llama/llama-3.3-70b-instruct:free",
    ],
    # Interviews and reports benefit most from a stronger model, so a hosted one goes first
    # when configured (unconfigured providers are skipped; on a laptop that means Ollama).
    Task.INTERVIEW_PLAN: _HOSTED_FIRST,
    Task.INTERVIEWER: _HOSTED_FIRST,
    Task.INTERVIEW_HINT: _HOSTED_FIRST,
    Task.INTERVIEW_REPORT: _HOSTED_FIRST,
    # Writing correct problems and solutions is hard for small models; hosted first.
    Task.QUESTION_GENERATE: _HOSTED_FIRST,
    Task.FRAMEWORK_GRADE: _HOSTED_FIRST,
    # Embeddings must come from ONE model: vectors from different models live in different
    # spaces and cannot be compared. So there is deliberately no cross-model fallback here.
    Task.EMBEDDING: ["ollama:nomic-embed-text"],
}

MOCK_MODEL = "mock-1"


@dataclass(frozen=True, slots=True)
class Route:
    provider: str
    model: str

    @classmethod
    def parse(cls, spec: str) -> "Route":
        provider, sep, model = spec.partition(":")  # models may contain ':' (qwen2.5:3b)
        if not sep or not provider or not model:
            raise ValueError(f"Invalid route '{spec}'; expected 'provider:model'")
        return cls(provider=provider.strip(), model=model.strip())

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


def routes_for(task: str, settings: Settings) -> list[Route]:
    specs = settings.llm_routes.get(task) or DEFAULT_ROUTES.get(task, [])
    routes = [Route.parse(spec) for spec in specs]
    if settings.llm_allow_mock_fallback and all(r.provider != "mock" for r in routes):
        routes.append(Route("mock", MOCK_MODEL))
    return routes
