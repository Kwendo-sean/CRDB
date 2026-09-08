# Google Forms / Sheets Sync

## Flow
Official Google Form → linked Google Sheet → configured `GoogleRegistrationSource` → background/manual sync service → Participant and SessionRegistration upserts → SyncLog.

## Configuration
Each source stores spreadsheet ID, worksheet name, header-to-field mappings, selected-session mappings and match priority. Default matching is canonical staff ID first, canonical email second. Names are never identity keys.

## Authentication
Use a Google service account with read-only access to the specific spreadsheet. Store its JSON outside the database in a secret manager or protected file referenced by environment variable. Share the Sheet with the service-account address.

## Upsert algorithm
1. Fetch headers and fail the run if required mapped columns are absent.
2. Normalise staff IDs (trim/case policy) and emails (trim/lowercase).
3. Validate each row and record explicit row errors.
4. In a transaction, lock any matching Participant by staff ID, then email.
5. If staff and email resolve to different people, reject for human resolution; never merge silently.
6. Update changed profile fields while preserving internal UUID, pass number, QR token, attendance and scores.
7. Create missing participant only when a configured unique identifier exists.
8. Upsert selected official sessions by stable source keys, not rewritten titles.
9. Commit cursor/last-sync only after the run completes.

## Operations
- `sync_google_registrations --source <id>` for manual/scheduled execution.
- Celery beat schedules incremental sync; a full reconciliation can be requested.
- Admin shows last successful sync, freshness, counts and rejected rows.
- Retries use exponential backoff; each run is idempotent.

## Privacy
Log row numbers and error categories, not full personal payloads. Restrict exports and Sheet credentials to authorised administrators.
