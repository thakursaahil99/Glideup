# ADR 0010 — Mock interviews: WebSocket streaming, engine, reports, editable prompts

- **Status:** Accepted (Phase 5)
- **Date:** 2026-10-05

## Context
Candidates practise a realistic interview: an AI interviewer asks questions, follows up, keeps
time and gives hints only when asked. Afterwards they get a scored report. Replies must stream
token by token. The local model is a 3B model on a laptop CPU, and it is unreliable at following
instructions. Admins must be able to change interview settings, rubrics and every prompt
without a deploy.

## Decision

**Transport: WebSocket with single-use tickets.** Browsers can't send auth headers on a
WebSocket, and our access tokens never reach browser JavaScript; they live in the BFF (ADR
0003). So the page asks the BFF for a ticket (`POST /interviews/{id}/ticket`). The ticket is
a JWT of type `ws`, valid 60 s and bound to one interview. The browser connects straight to
`API_PUBLIC_URL/ws/interviews/{id}?ticket=...`. Its `jti` is stored on the interview and
burned atomically on connect, so a ticket works once. The `Origin` header is checked against
`CORS_ORIGINS`. On connect the server sends the full state and transcript, so reconnecting
resumes exactly. Answers carry a `client_id` for idempotent resends.

**Streaming in the LLM gateway.** Providers gained `stream()` (Ollama NDJSON,
OpenAI-compatible SSE, mock). The gateway keeps routing, circuit breakers and usage logging.
It falls back to the next model only *before* the first token. After that it raises
`StreamInterruptedError` with the partial text, because switching models mid-sentence would
repeat or contradict what the user already saw. Timeouts: the provider timeout until the
first token, then 60 s between chunks.

**Engine (`app/modules/interviews/engine.py`), transport-independent.** Each action (start,
answer, hint, skip, end) runs under a per-interview lock. It persists its messages and emits
events. No DB transaction stays open while a model streams (ADR 0009 found that this blocks
schema changes). The interviewer decides between a follow-up and moving on with a `[[NEXT]]`
token, which the stream filter hides. Real-model testing showed what small models do with it:
`[NEXT]` variants, the token at the *start* of a reply, a reply that asks a question and also
says NEXT, and "Interviewer:" speaker labels. So:
- the filter strips every variant and a leading label, even when split across chunks;
- a reply ending in "?" counts as a follow-up;
- once the follow-up budget is spent, the server moves on without calling the model.

If no model answers, the interview advances with a neutral line instead of getting stuck.
Time is enforced by the server: on every action, every 5 s on an open socket, on read, and by
a scheduled job for abandoned interviews.

**Questions.** DSA, system design and behavioral rounds draw from a curated bank. It prefers
the chosen difficulty and avoids the user's recent questions; the Phase 6 question bank
replaces the bank file. Job-specific rounds are written by the LLM from the posting and the
resume, in the background. A deterministic plan is the fallback, so an interview can always
start.

**Reports (background job).** The model scores each rubric criterion (1–5) and each answered
question (0–10). The server then:
- grounds the draft: unknown criteria are dropped, and evidence must be a quote the candidate
  really said;
- forces unanswered questions to 0;
- computes the overall score itself: 60% weighted rubric, 40% per-question average.

So a generous model can't give a high score to someone who answered one of four questions.
Over-long text from the model is clipped rather than rejected. An interview with no answers
gets no report and makes no model call.

**Admin.** Interview types (duration, question count, follow-ups, difficulty, rubric) are
edited in **Admin → Interviews**. Interviews snapshot these settings, so edits never change a
running or finished one. Prompt templates are stored as immutable versions in Postgres:
- The shipped `.j2` files are imported as the first versions, and remain the fallback.
- Publishing or rolling back takes effect within 30 s (per-process cache) and is audited.
- Admin-written templates render in Jinja's **sandbox**, and may only use the variables the
  code passes for that template; this is validated on save.
- A playground runs any version, or unsaved text, through the production route with example
  values.

## Measured (laptop CPU, qwen2.5:3b via Ollama)
- First streamed token: 1.5–3.6 s warm (about 12 s while the model loads).
- Report: about 35 s.
- In a live run, all evidence quotes the model produced were real quotes. One report attempt
  failed validation twice; that led to clipping overlong fields.

## Consequences
- The per-interview lock is in-process: a deployment with several API workers needs sticky
  WebSocket routing or a Redis lock (Phase 9).
- Voice mode (Web Speech API) and a whiteboard for system design are Phase 8. For now,
  coding and design rounds have a text panel that is sent with each answer.
- Quality depends on the model. With a GitHub Models token, interviews and reports use it
  first, and the local model stays the fallback.
