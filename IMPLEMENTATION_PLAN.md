# Implementation Plan

## Goal
Deliver a production-shaped Django modular monolith for the Learning Week participation layer while preserving Google Forms as the registration authority and official spreadsheet content verbatim.

## Current context
Initial repository inspection found an empty, non-Git directory and no CRDB event-plan or quiz spreadsheet in the workspace/nearby uploaded files. Therefore architecture and import contracts can be implemented and tested now; official programme/questions remain empty until source files are supplied.

## Phase 0 — foundation
1. Create Django project, environment settings, dependencies and health endpoint.
2. Add core domain migrations, admin groups and audit infrastructure.
3. Add secure defaults, PostgreSQL/Redis production configuration and local SQLite fallback.
4. Add tests before each vertical feature slice.

## Phase 1 — participant identity
1. Implement Participant invariants and deterministic canonical matching.
2. Implement GoogleRegistrationSource and idempotent row upsert service/command.
3. Implement access lookup and persistent signed participant session.
4. Generate one opaque QR token/pass number per participant and render the mobile Learning Pass.

## Phase 2 — programme and check-in
1. Import exact sessions once source content is supplied.
2. Render grouped four-day programme and registration/attendance states.
3. Implement role-protected session selection and camera QR scanner.
4. Add transactional idempotent attendance service, duplicate state and audited override.

## Phase 3 — quizzes and prizes
1. Implement strict spreadsheet import/validation for exact ten-question rounds.
2. Implement quiz lifecycle and authenticated idempotent answer submission.
3. Persist official score independently from Learning XP.
4. Materialise daily and weekly rankings with documented tie-breaks.
5. Add facilitator controls, participant performance, prize verification and projector views.

## Phase 4 — PAL
1. Add signed, short-lived one-time launch tokens.
2. Add signed idempotent callback and minimal PALIntegrationResult persistence.
3. Award configurable XP/badge after verified completion.

## Phase 5 — engagement and operations
1. Add configurable XP rules, append-only transactions, badges and activity completions.
2. Add scoped Raspberry Pi/Arduino activity endpoint.
3. Add control-room analytics, exports, integration status and correction workflows.
4. Load/performance test peak quiz writes and cached leaderboards.

## Verification gates
- `python manage.py makemigrations --check --dry-run`
- `python manage.py migrate && python manage.py check --deploy`
- full Django tests, including identity conflicts, duplicate scans/submissions, closed questions, score separation, tie-breaks, callback replay and malformed imports
- static collection and production-settings check
- authenticated HTTP smoke flows
- desktop and true mobile browser inspection, QR scanability, overflow and accessibility checks
- 2,000-user load rehearsal against the deployed PostgreSQL/Redis topology

## Required handoff inputs
Official Google Form URL, Sheet ID/tab/header sample, registration column/session mappings, CRDB event-plan spreadsheet, CRDB quiz spreadsheet, approved logos/fonts/photography, PAL issuer/audience/endpoints/public keys and production infrastructure secrets.
