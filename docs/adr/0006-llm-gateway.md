# ADR 0006 — One LLM gateway: provider interface, routing, fallback, grounding, evals

- **Status:** Accepted (Phase 2)
- **Date:** 2026-10-01

## Context
GlideUp must run for free (a local Ollama model, the GitHub Models and OpenRouter free tiers)
and move to Azure OpenAI later with configuration only. Free tiers rate-limit, local models are
slow on a laptop CPU, and small models make mistakes. Every module (resume parsing now;
interviews, reports and question generation later) needs the same reliability features.

## Decision
All model calls go through `LLMGateway` (`backend/app/llm/`):

| Concern | How |
|---|---|
| Provider abstraction | `LLMProvider` protocol (`complete`, `embed`). Implementations: Ollama, one OpenAI-compatible class (GitHub Models, OpenRouter, later Azure OpenAI) and Mock. |
| Routing | Each task has an ordered `provider:model` chain (`routing.py`), overridable by the `LLM_ROUTES` env var (Phase 9: admin console). Unconfigured providers are skipped. |
| Fallback | Error, timeout or invalid output moves on to the next route. |
| Timeouts | Per provider (`LLM_PROVIDER_TIMEOUTS`), because a local 3B model on CPU needs minutes where a hosted API needs seconds. |
| Circuit breaker | Per provider: 3 consecutive failures open the circuit for 30 s, then one trial call is allowed through. |
| Structured output | JSON parsed tolerantly, validated by Pydantic, one "repair" round on the same model, then fallback. |
| Prompts | Versioned template files (`resume_parse.v2.system.j2`); the version is recorded on every call. |
| Prompt injection | Untrusted text is fenced in tags it cannot close; the system prompt marks it as data. |
| Grounding | After parsing, facts that are not in the source text are dropped (names, companies, institutions, links), and lazy uniform skill years/levels are cleared. This doesn't depend on the model resisting injection. |
| Usage logging | Every attempt (including failures) is written to `llm_usage` with tokens, latency, estimated cost, prompt version and user. |
| Mock provider | Configurable delay and error rate; heuristic per-task handlers; feature-hashed embeddings. It lets tests, CI and chaos tests run with no model, and is a last-resort fallback in local development only (refused in production). |
| Embeddings | One model per task, with **no cross-model fallback**: vectors from different models aren't comparable. |

## Evidence (golden-set evals, `python -m app.llm.evals.run`)
| Route / version | Mean score (0–1) | Notes |
|---|---|---|
| mock (heuristics) | 0.64 | Names, years and skills only; no companies or education |
| ollama qwen2.5:3b, prompt v1, 90 s timeout | 0.61 | One timeout; prompt injection changed the name |
| + per-provider timeout + grounding | 0.99 | Injection neutralised |
| prompt v2 (honest skill years) | 0.99 | Copied "10 years on every skill" removed |

## Consequences
- ✅ Switching to Azure OpenAI is a new route entry plus credentials.
- ✅ The app keeps working when any single provider is down (and with no LLM at all in local dev).
- ✅ Quality changes are measurable before rollout (evals), and traceable after (prompt version per call).
- ⚠️ Circuit state is per process; Phase 9 can move it to Redis.
- ⚠️ Semantic caching is deferred to Phase 9, as the build plan specifies.
