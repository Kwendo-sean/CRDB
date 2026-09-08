# Competition rules

Official prize ranking and general Learning XP are separate.

## Official score

Each official round contains ten questions. A correct answer receives the question's configured base points; an incorrect answer receives zero. The official source value is 1,000 points per question, producing 10,000 per day and 40,000 for the week. Speed bonus support is architectural only and disabled by default.

Daily ranking order:

1. Official daily score descending
2. Correct-answer count descending
3. Total valid response time ascending
4. Earliest completion timestamp
5. Stable attempt identifier

Weekly ranking sums authorised prize-eligible quiz attempts that contribute to the weekly competition. Learning XP never determines grand-prize position.

## Integrity

Database constraints prevent duplicate authorised attempts and duplicate attempt/question responses. Submissions carry UUID idempotency keys. Answers cannot change after a question closes. Participant identity is required.

Generated winner records begin `PROVISIONAL`. Operators may move them to `VERIFIED` or `WINNER`. Disqualification requires a reason and does not delete attempts or response evidence. Every Control Room mutation writes an `AuditEvent`.

Every accepted quiz response writes an immutable `ScoreTransaction` source entry with separate `competition_points` and `learning_xp` values. Attendance, activity and PAL completion entries carry Learning XP without affecting official standings. `source_type`, `source_id`, reason, status and idempotency key preserve provenance; authorised `QuizAttempt` totals are the fast ranking projection. Voiding or reversing a ledger entry retains its history.
