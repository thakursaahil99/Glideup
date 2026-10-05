# ADR 0013 — Application tracker, dashboard, voice mode, PWA and user reports

- **Status:** Accepted (Phase 8)
- **Date:** 2026-10-05

## Context
Phase 8 closes the journey: track applications, get reminded, see progress on one
dashboard, practise by voice, use GlideUp like an app, and tell us when something is wrong.

## Decision

**Tracker.**
- An application either references a board job (details copied from it, tracked once per
  user via a partial unique index) or is entered by hand.
- Seven statuses form the Kanban columns. A card has a position within its column, and
  inserting at a position shifts the others.
- Every create, status change and note is appended to `application_events`, the timeline
  shown on the card.
- Drag-and-drop uses native HTML5 events (no library). Every card also has a "Move to"
  select, so moving works by keyboard and screen reader.
- Moves are optimistic and roll back on error.

**Reminders** are stored per user (optionally tied to an application). A scheduled job
emails due reminders through SMTP: Mailpit locally, any provider in production, and off when
`SMTP_HOST` is empty. Each reminder is marked emailed *before* sending, so a crash can't
email twice; at worst one email is lost, and the reminder still shows in the app.
Rescheduling re-arms the email.

**Dashboard: one aggregate endpoint.** It returns:
- applications by status;
- the interview score trend (last 10 reports);
- verified skills (radar);
- weak topics (rubric criteria averaging 2.5/5 or less in recent reports, and framework-test
  sections under 50%);
- the practice streak (consecutive days with a submission, interview or test; today counts
  as kept until it ends);
- upcoming reminders;
- a rule-based recommended next step (resume → follow-ups due → pick jobs → interview →
  test → weakest topic).

The rules are deterministic and tested. Charts are single-series in one brand hue, with
tooltips and no legend (the card title names the series).

**Voice mode** uses the browser's free Web Speech API: dictation appends to the answer, and
"Read aloud" speaks each new interviewer message. Both appear only when the browser supports
them; text always works.

**PWA.**
- A web manifest with maskable icons rendered from the SVG logo, plus a service worker.
- The service worker is deliberately conservative: it caches immutable build assets and
  icons, and an offline page shown only when navigation fails. It never caches API calls,
  auth or page HTML, so no user data sits in the cache.
- It is registered in production builds only. The auth proxy skips `sw.js` and
  `offline.html`.

**User reports.** "Report a problem" sits on job pages (broken link), problems (wrong
question) and interview reports (bad AI feedback). It is limited to 20 per user per day.
Admins see an open/resolved/dismissed queue: support can read it (`reports:read`), admins
resolve, dismiss and reply (`reports:manage`, audited), and the user sees the reply.

## Consequences
- Reminder emails need an SMTP provider when GlideUp goes live; until then they're in-app
  only.
- Speech recognition availability varies by browser (Chrome and Edge have it; Firefox
  doesn't).
- The service worker's cache version must be bumped if its caching rules change.
