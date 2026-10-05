"""Application metrics for Prometheus (HTTP metrics come from the instrumentator)."""

from prometheus_client import Counter, Histogram

LLM_CALLS = Counter(
    "glideup_llm_calls_total",
    "LLM calls by task, provider and outcome",
    ["task", "provider", "outcome"],
)
LLM_LATENCY = Histogram(
    "glideup_llm_latency_seconds",
    "LLM call latency",
    ["task", "provider"],
    buckets=(0.25, 0.5, 1, 2, 5, 10, 20, 40, 80, 160),
)
LLM_TOKENS = Counter("glideup_llm_tokens_total", "Tokens used", ["task", "provider", "kind"])
LLM_CACHE = Counter("glideup_llm_cache_total", "LLM response cache lookups", ["task", "result"])
RATE_LIMITED = Counter("glideup_rate_limited_total", "Requests rejected by rate limits", ["bucket"])
SUBMISSIONS = Counter(
    "glideup_submissions_total", "Graded code submissions", ["language", "verdict"]
)
BACKGROUND_JOBS = Counter("glideup_background_jobs_total", "Background jobs", ["job", "outcome"])
