# CRDB X PAL Learning Week Experience — Architecture

## Product boundary
Google Forms remains the formal registration system. This application starts at the participant identity created from the configured Google Sheet and provides the persistent Learning Pass, programme, attendance, quizzes, prize ledgers, PAL hand-off, expo activity, badges, and operational analytics.

## Delivery architecture
- Django 5.2 modular monolith with server-rendered, mobile-first templates and small progressive JavaScript modules.
- Django REST Framework for scanner, PAL callback, activity-device and live-state APIs.
- PostgreSQL in production; SQLite is permitted only for local development.
- Redis for cache, rate-limit counters, Channels groups and Celery broker/results.
- Celery workers perform Google Sheet sync, aggregate refresh, badge evaluation and retries.
- Django Channels broadcasts low-volume quiz state events. Answers are persisted over HTTP and never trusted to transient WebSocket state.
- Static assets are served by WhiteNoise behind the production reverse proxy/CDN.

## Modules
`core` owns the domain model, services, HTTP views, APIs, import commands and admin. Domain services isolate identity resolution, Sheet sync, attendance, scoring, leaderboard materialisation, PAL signing, and activity completion.

## Trust boundaries
1. Browser sessions are untrusted; participant IDs are stored in signed server sessions.
2. QR values are random opaque tokens, never staff IDs or personal data.
3. Google credentials stay server-side and are scoped read-only.
4. PAL launch tokens are signed, short-lived and audience-bound; callbacks are signed, replay-protected and idempotent.
5. Device/API credentials are hashed, scoped to one activity and rate limited.
6. Admin mutations require authenticated role permissions and generate audit events for attendance/score/winner changes.

## Scale and reliability
- Indexed lookup keys: canonical staff ID, canonical email, QR token hash, session start, attendance uniqueness, quiz state, attempt participant/quiz, response attempt/question, score ledger participant/category.
- Cache public leaderboards and per-participant rank snapshots; invalidate after committed score changes.
- Quiz submissions use database transactions and uniqueness constraints. Clients receive an idempotent submission ID and may safely retry.
- WebSockets publish state only; database rows are authoritative.
- Use connection pooling, bounded Channels groups, precomputed leaderboard snapshots and pagination.
- Health endpoints expose application, database, cache and worker freshness separately.

## Deployment
Reverse proxy/load balancer → multiple ASGI workers → Django. PostgreSQL is the system of record; Redis is disposable coordination state. Run Celery worker and beat separately. Store secrets in the deployment secret manager. Enforce TLS, secure cookies, HSTS, CSRF protection, CSP, request-size limits and structured logs.

## Phases
1. Identity sync, participant lookup, Learning Pass and QR.
2. Programme, registrations and idempotent QR attendance.
3. Auditable quizzes, control state, daily/weekly rankings and winner verification.
4. PAL signed launch and callback.
5. Badges, activity API, analytics and production hardening.

## Source-content rule
The repository contained no CRDB programme or quiz spreadsheet at initial inspection. The implementation must import official content once supplied and must not invent official session titles or questions.
