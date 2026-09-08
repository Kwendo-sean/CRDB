# Quiz Engine

## Authoritative scoring
Each official question awards its configured base points (source default 1,000) only when correct; incorrect awards zero. Speed bonus exists as a configuration capability but is disabled by default and contributes zero unless organisers explicitly enable and document it.

Official weekly score = sum of the participant's authorised official attempt score for each of the four prize-eligible quizzes. This competition score is separate from Learning XP.

## Lifecycle
Draft → lobby → question open → question closed → answer revealed → leaderboard → next question → finished. The database stores current state and timestamps. Channels broadcasts state changes but is not authoritative.

## Submission transaction
The HTTP answer endpoint authenticates the Learning Pass session, locks the attempt/question state, validates the unique submission UUID, confirms the question is open and within the authoritative deadline, rejects duplicate attempt/question responses, snapshots correctness/points/duration, updates attempt aggregates, and commits before acknowledging.

## Integrity
- No anonymous attempts.
- One authorised official attempt per participant/quiz by default.
- Unique attempt/question and submission UUID constraints.
- No edits after close.
- Server timestamps define eligibility; client timers are display only.
- Every manual adjustment includes administrator, before/after values, reason and timestamp.

## Ranking
Daily: score descending, correct-answer count descending, total valid response time ascending, completion time ascending, stable participant UUID final fallback. Store calculated daily ranks when a round is finalised.

Weekly grand prize: sum official daily scores, then cumulative correct count, cumulative valid response time and latest required completion timestamp. Materialise/cache snapshots and clearly identify Top 10. Winner records move through PROVISIONAL → VERIFIED → WINNER; DISQUALIFIED is explicit and audited.

## Import validation
The XLSX/CSV importer requires day, challenge, question number/text, four answers, correct-answer number 1–4, valid 20/30-second timer (or organiser-approved configured value), positive points and host note. Each official challenge must contain exactly 10 unique question numbers. Any malformed row rejects the import transaction and produces administrator-visible errors; rows are never silently skipped. The Control Room previews detected/valid/error totals before import and replaces questions only on the selected quiz.

## Live delivery
Facilitator mutations are staff-protected. WebSocket groups receive compact state events, while `/api/quizzes/<id>/state/` remains the canonical recovery path. Participant clients reconnect automatically, poll REST while disconnected, restore the current question, and retry a locally persisted answer with its original submission UUID. The answer endpoint remains authoritative and idempotent.

Daily/weekly projections are queried from attempt aggregates rather than recalculated from raw responses. A production spike test is still required to set the final Redis leaderboard cache TTL and Gunicorn worker count for the target VPS.
