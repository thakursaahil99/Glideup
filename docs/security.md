# Security checklist (OWASP Top 10, 2021)

| Risk | How GlideUp handles it |
|---|---|
| A01 Broken access control | RBAC permissions checked on every admin route. Resources are always scoped to the owner (`user_id` in every query). Admin pages 404 for users without the permission. |
| A02 Cryptographic failures | No passwords are stored: sign-in is Google OAuth (ID token verified against Google's JWKS, audience-checked). Short-lived JWT access tokens and rotating refresh tokens live in httpOnly, SameSite cookies held by the BFF. HSTS in production. Secrets only via env vars. |
| A03 Injection | SQLAlchemy bound parameters only. Prompt templates render in Jinja's sandbox. User code runs only inside the sandbox (Piston/Judge0), never on the host. |
| A04 Insecure design | Rate limits per user on expensive endpoints. Per-user LLM token budgets. Feature flags to switch a feature off quickly. |
| A05 Security misconfiguration | Security-headers middleware and CSP on the API and the web app. `/docs` hidden in production. `.env` never committed. |
| A06 Vulnerable components | Pinned dependencies (uv.lock, package-lock.json). CI runs the tests on every push. |
| A07 Auth failures | Refresh-token rotation with reuse detection (all sessions revoked). Single-use 60-second WebSocket tickets with an Origin check. Dev password-less login is refused outside local/test. |
| A08 Integrity failures | Resume uploads are checked by magic bytes (`%PDF-`) and size-capped. No deserialization of untrusted data formats. |
| A09 Logging and monitoring | Structured logs with request ids. Audit log for admin actions. Prometheus metrics, Grafana dashboard, and the System Health page with failed jobs. |
| A10 SSRF | Outbound fetches go through `safe_fetch`, which blocks private and loopback addresses and limits redirects. Job sources are allow-listed APIs only, with no scraping of sites whose terms forbid it. |

Report a vulnerability privately to the maintainers rather than in a public issue.
