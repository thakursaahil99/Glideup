# ADR 0009 — Match score, skill gap and recommendations

- **Status:** Accepted (Phase 4)
- **Date:** 2026-10-05

## Context
Every job should show how well the signed-in user fits it ("82% match") and which skills are
missing, and users need a feed of the jobs that fit them best. Inputs: the parsed resume (and
any GitHub/portfolio analysis), about 15,000 live jobs, a laptop CPU, and a small local LLM
that takes 10–60 s per call. Scores must stay honest when parts of the pipeline are down.

## Decision

**Embeddings.** Jobs and resumes are embedded with one model (`nomic-embed-text`, 768-dim)
into pgvector, with an HNSW index (cosine) for nearest-neighbour search. Following the
model's training, the resume is the *query* (`search_query:` prefix) and jobs are
*documents* (`search_document:`). A job's text is its title, company, level, skills and the
first 1,500 characters of the description. That is enough to say what the role is, and it
keeps CPU cost at about 4 jobs per second.

Every vector stores a key such as `ollama:nomic-embed-text#t1` (provider, model,
text-recipe version). Only vectors with the current key are stored or compared. If the
gateway falls back to another model, the run stops instead of mixing vector spaces.
Changing the model or the recipe bumps the key, and everything re-embeds. Jobs store the
`content_hash` they were embedded from, so edited postings re-embed. A backfill runs after
every ingestion run and every 15 minutes. It embeds newest first, commits per batch, and
holds a Postgres advisory lock so only one runs at a time.

**Score (0–100), computed on request.** In `app/modules/matching/scoring.py`, pure and
deterministic:

- **semantic** (weight 0.6): cosine rescaled from the range real pairs fall in. Measured on
  a real resume against 3,456 live jobs, unrelated roles (recruiting, sales) score
  0.49–0.57, the median job 0.65 and the best fits 0.78–0.80. So 0.58 maps to 0 and 0.78
  to 1.
- **skills** (weight 0.4): share of the job's detected skills the user has, from the resume
  or GitHub/portfolio. A closely related skill counts half (MySQL ← PostgreSQL, Vue ← React).
  The weight shrinks when a posting names fewer than three skills.
- **level** multiplies the result, from 0.7 to 1.0, by years of experience against the band
  the level implies. It can only lower a score. A first version averaged it in as a third
  signal; the eval showed it lifting unrelated jobs (a sales role scored 69 for a backend
  engineer, because seven years fit "senior").

Unknown signals are left out, not guessed. Without a usable resume vector (Ollama down, or
the resume not re-embedded yet) the score comes from skills and level, is marked `partial`
in the UI, and a re-embed is queued.

Scores are not stored. A page of 20 jobs costs one query for 20 vectors plus arithmetic, so
scores always reflect the current resume and job, and there's no N×M table to keep fresh.

**Recommendations.** The 400 nearest jobs by vector, re-ranked by the full score plus small,
explained nudges: preferred city/state/country (+6/+4/+2), remote preference (+5, or −8 for
on-site when the user wants remote), posted in the last 14 days (+2). Each card shows why it
was recommended. Users with skills but no vector get the jobs that mention their skills,
newest first.

**AI skill gap, on demand.** The deterministic part (matched / close / missing skills) is
instant and free. The LLM explanation runs only when the user asks, in the background, and
is stored in `job_matches`. A stored analysis is tied to the resume, the job's content
hash, a fingerprint of the user's skills and years, and the prompt version (`skill_gap@v1`).
Any change marks it stale, and the user can refresh it. Its output is **grounded**: a
"missing" skill must appear in the posting and must not be one the user has, and a "weak"
skill must be one the user has. The posting and profile are fenced as untrusted data in the
prompt. A per-user daily limit (`MATCH_ANALYSIS_DAILY_LIMIT`, default 30) caps LLM cost.

## Measured
`python -m app.llm.evals.match`: 3 golden candidates × 4–5 human-graded jobs, through the
production embedding and scoring code. Calibrated version: pairwise ordering **0.96**, best
job ranked first **3/3**, strong ≥ 65 and poor ≤ 35 in **100%** of cases. The first version
(guessed calibration, level averaged in) scored 0.89 / 3/3 / 50%.

## Consequences
- Match quality depends on the embedding model. Changing it is a config change plus a
  re-embed (≈ 1 hour for 15k jobs on a laptop CPU, seconds on a hosted API). The eval should
  be re-run and `SEMANTIC_FLOOR/CEILING` re-checked.
- Skill comparison only knows the skills in the taxonomy (`app/modules/resumes/skills.py`).
  The semantic signal covers the rest, and the taxonomy becomes admin-editable in Phase 9.
- No stored scores means no "sort all search results by match". The recommendations feed
  covers that need, from a bounded candidate pool.
- The admin console shows embedding coverage and can trigger a backfill (audited).
