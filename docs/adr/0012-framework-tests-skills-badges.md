# ADR 0012 — Framework tests, verified skill scores and badges

- **Status:** Accepted (Phase 7)
- **Date:** 2026-10-05

## Context
Beyond algorithm problems, candidates need to prove framework skills (React, FastAPI, ...)
the way interviews test them: knowledge, reading others' code, explaining concepts and
building something small. Results should turn into skill levels a candidate can show, and
the brief asks for badges.

## Decision

**One timed test per framework, four question types**, stored in the question bank with a
`type`, a `framework_key` and type-specific `content` that is validated with Pydantic:

| Type | What the user does | How it is graded |
|---|---|---|
| mcq | Picks an option | Exact match |
| review | Writes a code review of a snippet with planted issues | The LLM marks which planted issues were found |
| viva | Explains a concept | The LLM marks which key points were covered |
| project | Writes a small component or endpoint | Static pattern checks plus the LLM per requirement |

The default composition is 6 MCQ, 1 review, 2 viva and 1 project in 40 minutes; it is
admin-editable per framework. Tests draw unseen questions first. Answers autosave, and
time is enforced on the server, with a 2-minute grace for the last autosave.

**Scores are computed by us, not by the model.** The LLM only judges each rubric item as
yes, partial or no; we turn those into weighted credit. For project requirements that have
a pattern:
- if the pattern is missing, the item scores 0 whatever the model says;
- if it is present, the item gets at least half credit.

Sections are weighted MCQ 30%, review 20%, viva 20%, project 30%, renormalised over the
sections the test contains. Levels: under 40 beginner, under 60 intermediate, under 80
advanced, otherwise expert. Empty answers score 0 without a model call. Secrets never reach
the browser before grading: MCQ answers, planted issues, key points and requirement
patterns. If grading fails because no model is available, the attempt is marked `failed`
and can be resubmitted.

We don't run React or FastAPI projects. They need package installs that the sandbox
deliberately can't do (no network), so projects are judged statically. The UI says these
are AI-reviewed.

**Verified skills.** `skill_scores` keeps the best score per skill, so a bad day doesn't
erase a proven level:
- **Frameworks:** from tests.
- **Languages:** from solved coding problems (easy 10, medium 20, hard 35 points, capped at
  100).

**Badges** are rules in code, re-evaluated after each graded test, accepted submission and
interview report:
- first solved problem;
- 5 problems solved;
- 3 languages;
- interview score of 70 or more;
- practitioner (60+) and expert (85+) per framework.

**Seed content:** React and FastAPI, 13 questions each. MCQ options are rotated per question
when seeded, using a stable hash, so the correct answer isn't always in the same position
(the source data lists it second).

## Consequences
- Project grading depends on the model for requirements without a pattern; patterns give a
  floor and ceiling that the model can't override.
- Adding a framework is admin work (a framework row plus questions), not a code change.
