# Go-live checklist

Everything here is ordered. Work top to bottom; do not skip the preflight.

## 1. Server (once, ~20 minutes)

On a fresh Ubuntu LTS VPS with DNS already pointing at it:

```bash
git clone <repo> crdb-learning-week && cd crdb-learning-week
cp .env.example .env
nano .env          # see section 2
sudo bash server_setup.sh
docker compose exec web python manage.py create_operator admin --superuser
```

`server_setup.sh` installs Docker, opens the firewall, generates any missing
secrets, sets `DJANGO_ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` / `APP_BASE_URL`
from your `DOMAIN`, runs a configuration preflight, migrates, collects static
assets, provisions Let's Encrypt TLS, installs the nightly backup cron and
verifies `/health/`. It stops with a readable message if anything is wrong.

## 2. Values you must set in `.env`

| Key | Why it matters |
| --- | --- |
| `DOMAIN`, `SSL_EMAIL` | Drives TLS, allowed hosts and CSRF origins. Without `DOMAIN` the site serves plain HTTP on the server IP. |
| `DJANGO_DEBUG=0` | Required for production. The app refuses to start with the placeholder secret key while `DEBUG=0`. |
| `OFFICIAL_REGISTRATION_URL` | The "register now" link shown to anyone not on the roster. |
| `ACTIVITY_API_KEY` | Only if expo/AIoT stand devices will mark activities complete. |
| `PAL_CALLBACK_SECRET` | Only if the PAL AI Jobs integration is live. |

`DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `DATABASE_URL` and `ACTIVITY_API_KEY`
are generated for you if left blank.

## 3. Preflight — run this before you load any data

```bash
docker compose exec web python manage.py check --deploy
```

It must report **no ERRORs**. The event-specific guards catch the four
configuration mistakes that only surface under load:

| ID | Meaning |
| --- | --- |
| `core.E001` | `REDIS_URL` unset. Live quiz broadcasts would reach only the players attached to one Gunicorn worker. |
| `core.E002` | Still on SQLite. It serialises writes and stalls when 2,000 people answer at once. |
| `core.E003` | `DJANGO_ALLOWED_HOSTS` still local-only. Every request would be rejected. |
| `core.E004` | HTTPS on but `CSRF_TRUSTED_ORIGINS` empty. Every form post and every answer submission would fail CSRF. |

Warnings (`core.W001`–`W003`) are optional integrations; they will not block you.

## 4. How people get in

Participants go to `/access/`, type their work email and they are in. If the
email is already on the roster they sign straight in; if it is new they give a
name (and department) and get their Learning Pass immediately. No passwords, no
accounts, no Google Form required.

Pre-loading a roster still works and takes priority — a match on email or staff
ID always signs in rather than creating a second record — so you can import a
spreadsheet, sync a Google Form, let people self-register, or mix all three.

Control this at **Control Room → System → Event Settings**:

| Setting | Effect |
| --- | --- |
| `Self registration enabled` | Off = only pre-loaded people can get in (the old behaviour). |
| `Allowed email domains` | Comma-separated, e.g. `crdbbank.co.tz`. **Blank means any email address on the internet can join and appear on the prize leaderboard.** Set this before opening the doors. |
| `Self registration collects department` | Off = ask for name and email only. |

## 5. Load the event data

All four spreadsheets are downloadable from inside the Control Room, and every
one carries an INSTRUCTIONS sheet plus two worked example rows to overwrite.

| What | Download & upload at | Load first? |
| --- | --- | --- |
| Participants (the roster) | Participants → **Import from Excel** | **Yes — everything else depends on it** |
| Programme sessions | Programme → Sessions → **Import from Excel** | Yes |
| Interactive games / expo / AIoT | Experiences → Activities → **Import from Excel** | Yes |
| Quiz questions | Experiences → Quizzes → *a round* → **Import Questions** | Per round, after creating the round |

For a very large roster you can also load from the command line:

```bash
docker compose exec web python manage.py import_participants /path/roster.xlsx
docker compose exec web python manage.py import_sessions     /path/programme.xlsx
docker compose exec web python manage.py import_activities   /path/games.xlsx
docker compose exec web python manage.py make_templates --output /tmp/templates
```

Every importer is all-or-nothing. If one row is wrong, nothing is saved and you
get the exact row number and reason. Re-importing a corrected file **updates**
existing records rather than duplicating them, matched on:

- participants → staff ID, then email
- sessions → `source_key`
- activities → `code`

Existing Learning Passes, QR codes, attendance and scores are never touched by a
re-import.

## 6. Build and publish each quiz round

A complete worked example ships with the project:
`import_templates/sample-quiz-day1-ai-infrastructure.xlsx` — ten valid questions
on AI in banking, also downloadable from the Import Questions page. Import it as
a dry run before the event, or edit it into your own round.

1. Experiences → Create Experience → **Quiz**. Enter the basics and save.
2. **Import Questions** (or add ten by hand). Choose *Validate & Preview* first.
3. **Publish / Schedule Quiz** — blocked unless there are exactly ten questions,
   each with four answers and exactly one correct answer.
4. A round cannot be launched from the host screen until it is published, and
   once anyone has answered, its questions are locked against replacement.

## 7. Day-of running order

- **Expo games**: Control Room → **SCAN A PASS** (top bar of every page). Choose
  the game once, then scan each Learning Pass. That game's points are awarded on
  the spot; scanning the same pass twice at the same game does not pay twice.
  The same screen also does session check-in — just pick a session instead.
- **Live round**: Control Room → Quizzes → the round → **Control** → **START THE
  ROUND**. That is the only press. All questions launch at once and run on their
  own timers, opening, closing and revealing without any further host action.
  Set the pace per question (5s–1h) in the round's settings.
- **Projector**: `/display/leaderboard/` for the week,
  `/display/leaderboard/<quiz id>/` for a single round.
- **Results**: Competition → Generate provisional results → review →
  Verify / Winner. Disqualification requires a reason and is audited.

Participants sign in at `/access/` with their email (or staff ID). There are no
passwords to issue and no accounts to create.

What a participant sees, and nothing else:

| Screen | Purpose |
| --- | --- |
| **Quizzes & Games** (`/dashboard/`) | Total points, the quiz rounds, the interactive games. The single hub. |
| **Leaderboard** (`/leaderboard/`) | Weekly standings and their own position. |
| **My Pass** (`/pass/`) | The QR code shown at a stand to collect game points. |

The programme/timetable is no longer part of the participant app. Sessions and
QR check-in remain in the Control Room for staff, and attendance still awards
Learning XP toward each person's total.

## 8. What happens when something goes wrong

| Situation | Behaviour |
| --- | --- |
| A participant's phone drops off Wi-Fi mid-question | The answer is held in their browser and retried with its original submission ID. Duplicate submission is impossible. |
| A participant taps an answer after the timer ran out | They are told "TIME UP / THIS QUESTION IS CLOSED". The answer is discarded, not retried. |
| The host walks away without closing a question | The question closes itself on the timer and the answer is revealed. |
| The host loses their laptop mid-round | The round keeps running: the schedule is stored, so every player continues on the clock. |
| A player arrives after the round started | They can still join and answer the remaining questions. |
| WebSockets blocked on the venue network | Clients fall back to polling `/api/quizzes/<id>/state/` every 3 seconds. The database stays authoritative. |
| Redis goes down mid-round | Host actions still succeed; the broadcast failure is logged and clients recover by polling. |
| Someone double-taps Join | One attempt only, enforced by a database constraint. |
| A stale session cookie survives a data restore | The visitor is signed out cleanly rather than hitting an error page. |
| Two scanners check the same person in at once | One attendance record; the second returns a clear conflict message. |

## 9. Backups

`server_setup.sh` installs a nightly dump at 02:15 into `backups/`. Take a manual
one before each day's rounds:

```bash
./scripts/backup_database.sh
```

Restore is `./scripts/restore_database.sh <file>`. See `BACKUP_RESTORE.md`.

## 10. Updating after go-live

```bash
sudo ./deploy.sh
```

Rebuilds, migrates, recollects static assets and verifies health. Do this
between rounds, never during one.

## 11. Capacity notes

Sized and query-shape tested at 2,000 participants:

- Live quiz state polling reads a shared 3-second cache, so the poll cost does
  not grow with the number of players.
- The weekly leaderboard is cached for `LEADERBOARD_CACHE_SECONDS` (default 15).
- Sessions read from Redis and write through to PostgreSQL.
- Rate limits protect sign-in, answer submission and state polling; retune via
  the `RATELIMIT_*` values in `.env` without a code change.

Raise `WEB_WORKERS` only after watching PostgreSQL and Redis saturation under a
real spike. Start at 4.
