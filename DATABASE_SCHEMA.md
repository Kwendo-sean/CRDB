# Database Schema

## Identity and access
### Participant
UUID primary key; canonical unique staff ID and email (nullable individually, at least one required by validation); full name; department; job role; phone; random QR token hash; public pass number; source registration timestamp; active state; created/updated timestamps. Personal fields are excluded from public leaderboards.

### Admin roles
Django users and groups: Super Admin, Event Admin, Check-in Staff, Quiz Facilitator, Analytics Viewer. Permission checks are server-side.

## Programme
### Session
Day, start/end, exact official title, facilitator, format, audience, location, capacity, active flag.

### SessionRegistration
Unique participant/session pair; source and source row key; selected timestamp.

### Attendance
Unique participant/session pair; checked-in timestamp; scanner/admin; source; override flag and note. Duplicate scans return the existing record.

## Quiz competition
### Quiz
Official day/challenge name, sequence, state, prize eligibility, speed-bonus configuration (disabled by default), attempt limit and timestamps.

### Question / AnswerChoice
Question sequence and exact source text, timer, configured base points, host note; exactly four ordered choices; one correct choice. Published official rounds validate exactly ten questions.

### QuizAttempt
Unique authorised participant/quiz attempt unless an administrator opens another. State, started/completed timestamps, official flag, score, correct count, total valid response milliseconds, completion order/time and final daily rank.

### QuizResponse
Unique attempt/question and globally unique submission UUID. Selected choice, immutable correctness snapshot, awarded base points, speed points, response duration, received timestamp and acceptance state.

### ScoreAdjustment / AuditEvent
Every manual score mutation stores actor, old/new values, reason and timestamp. Official totals are recomputed from accepted responses plus explicit adjustments, never edited invisibly.

### WinnerRecord
Quiz/day or weekly scope, calculated rank, final rank, score snapshot, correct/time tie-break snapshot and status: provisional, verified, winner or disqualified.

## Engagement
### ScoreTransaction
Append-only Learning XP ledger with participant, category, points, unique idempotency key, source object reference, actor and timestamp. Learning XP is distinct from official quiz competition score.

### Badge / ParticipantBadge
Configurable badge criteria metadata; unique participant/badge award with evidence and timestamp.

### Activity / ActivityCompletion
Configurable expo/PAL/other activity and points; unique idempotent completion per participant/activity unless repeatable.

### PALIntegrationResult
Participant, external result ID, launch nonce, completion state, role/career, optional numeric risk score/Career HP, minimal skill-gap and recommendation summaries, risk-card URL, raw payload checksum and timestamps.

## Integrations
### GoogleRegistrationSource
Spreadsheet ID, worksheet, encrypted credential reference, JSON column mapping, ordered unique identifiers, last sync cursor/time and enabled state.

### SyncLog
Source, started/completed timestamps, status, rows read/created/updated/rejected, structured row errors and cursor.

## Core constraints
- Unique canonical staff ID and canonical email when present.
- Unique attendance(participant, session).
- Unique session registration(participant, session).
- Unique quiz response(attempt, question) and submission UUID.
- Unique official active attempt(participant, quiz) enforced in service/transaction with database locking.
- Non-negative response duration and awarded competition points.
- Winner and score changes are audit logged.
