# Control Room guide

Django's `/admin/` is a low-level superuser recovery surface only. Normal event operations happen at `/control/`.

## How participants get in

Participants go to `/access/` and enter their work email. Known emails sign
straight in; new ones give a name and department and receive a Learning Pass
immediately. No passwords, no Google Form.

Pre-loading a roster (Excel import or Google sync) still works and takes
priority — a match on email or staff ID always signs in rather than creating a
second record.

Tune this under System > Event Settings:

- **Self registration enabled** — off restores the old pre-loaded-only behaviour.
- **Allowed email domains** — comma-separated, e.g. `crdbbank.co.tz`. Blank means
  any address on the internet can join and appear on the prize leaderboard.
- **Self registration collects department** — off asks for name and email only.

## Sign in

Open `/control/login/`. Successful staff authentication routes to `/control/`, not Django Admin.

Create or reset an operator account:

```bash
python manage.py create_operator <username> --superuser        # prints a generated password
python manage.py create_operator <username> --password '...'   # or set one yourself
```

Running it against an existing username resets that operator's password.

## Load data from Excel

Every bulk surface has a downloadable template with an INSTRUCTIONS sheet, the
exact column names and two worked example rows to overwrite.

| Data | Where | Matched on re-import |
| --- | --- | --- |
| Participants | Participants > Import from Excel | staff ID, then email |
| Programme sessions | Programme > Sessions > Import from Excel | `source_key` |
| Interactive games, expo stands, AIoT demos | Experiences > Activities > Import from Excel | `code` |
| Quiz questions | Experiences > Quizzes > a round > Import Questions | replaces that round only |

Load participants first; the rest of the event depends on the roster.

Imports are all-or-nothing. A single bad row rejects the whole file and reports
the exact row number and reason, so rows are never silently skipped. Re-importing
a corrected file updates existing records instead of duplicating them, and never
disturbs existing Learning Passes, QR codes, attendance or scores.

Command-line equivalents, useful for a very large roster:

```bash
python manage.py import_participants roster.xlsx
python manage.py import_sessions programme.xlsx
python manage.py import_activities games.xlsx
python manage.py import_quizzes questions.xlsx
python manage.py make_templates --output ./import_templates
```

## Awarding points at an expo game

The QR scanner is on every Control Room page — **SCAN A PASS** in the top bar,
or QR Scanner in the sidebar.

1. Choose the game at the top of the scanner (VR Games, Robot Assembly, Arduino
   Assembly, or a session for check-in). The choice is remembered between scans,
   so a stand operator picks it once at the start of their shift.
2. Press **START SCANNING** and point the camera at each Learning Pass. The
   camera keeps running between people, so you can work through a queue.
3. Each scan shows the person's name, the game, the points awarded and their new
   total.

Points are per game: each game pays its own value, and scanning the same pass
twice at the same game reports "already awarded" rather than paying again.
Someone can collect from every game, once each.

If the camera fails, open **Camera not working?** and type the pass number.

Change a game's points at Experiences > Interactive Games, or load them in bulk
from the activities spreadsheet.

## What participants see

Three screens only: **Quizzes & Games** (their total points, the rounds and the
games), **Leaderboard**, and **My Pass** (the QR shown at stands). The programme
timetable is not part of the participant app.

Sessions and the QR scanner stay here in the Control Room. Checking someone into
a session still awards Learning XP, which counts toward their total points.

## Programme

- List sessions: `/control/programme/sessions/`
- Create a session: `/control/programme/sessions/create/`
- Select any session row to edit its time, facilitator, location, audience, format, capacity, or active state.

Creating a session also creates its participant-facing Experience. Check-in remains at `/control/scanner/`.

## Create a quiz

1. Open `/control/experiences/create/`.
2. Select **Quiz**.
3. Enter basics, competition settings, theme, date, and time.
4. Save and continue to the question builder.
5. Use **Add Question** for question text, 20/30-second timer, 1,000 points, four answers, one correct answer, and host note.
6. Repeat until all ten questions are present, or use **Import Questions** for an official XLSX/CSV file. Download the template from that page first. Select **Validate & Preview**, review detected/valid/error totals, then select the same file and **Import Questions**. Import replaces questions only for the selected quiz, and is refused once participants have answered that round.
7. Select **Preview**. Preview creates no participant attempt and no score.
8. Select **Publish / Schedule Quiz**. Publication is blocked unless there are exactly ten questions and every question has four answers and one correct answer.
9. Select **Control** to run the round live. A round that is still a draft cannot be launched.

## Running a round live

**You press START once. The whole round then plays itself.**

Every question is launched at that moment with its own open and close time
worked out from its time limit. Nothing comes back to ask you to advance it:

```
START THE ROUND
   -> 10s countdown
   -> question 01 opens, runs its timer, closes, answer revealed for 8s
   -> question 02 ... and so on to the last question
   -> round finished, scores final
```

The host screen becomes a monitor: live answer counts, the countdown, and the
time the round ends. There is no next-question button because there is nothing
to press.

Set the pace per round under Quiz settings:

| Setting | Meaning |
| --- | --- |
| Time limit (per question) | 5 to 3600 seconds. 20 or 30 for a fast round, 300 for five minutes. Each question can differ. |
| `reveal_seconds` | Seconds spent showing the correct answer between questions. Default 8. |
| `lobby_seconds` | Countdown after pressing START before question 1 opens. Default 10. |
| `auto_run` | Turn **off** for the old host-paced mode, where you advance each question yourself. |

Players can join any time from when the round is scheduled until it finishes,
so nobody is locked out by the short lobby, and latecomers simply miss the
questions that already ran.

`STOP & RESET THE ROUND`, jumping to a specific question and the other manual
controls are under **Other controls**. Jumping to a question switches the round
to host-paced.

Open `Projector view` on the room screen so everyone sees the standings.

## Verify winners

1. Open `/control/competition/`.
2. Generate provisional results for the completed daily round.
3. Review score, correct count, and total valid response time.
4. Use **Verify** or **Winner** only after review.
5. Disqualification requires a reason and retains historical scores. **Restore** returns the record to provisional.

## Other experiences

- Expo activities, AIoT demos and custom challenges can be loaded in bulk from Excel (see above), or created one at a time: choose the specific type at `/control/experiences/create/`; each is stored as its own Experience type and appears under `/control/experiences/activities/`.
- PAL settings and Google sources: `/control/integrations/`
- Badges and XP rules: `/control/rewards/`
- Event visibility and support details: `/control/system/settings/`
- Administrative history: `/control/system/audit/`
- Registration and attendance analytics: `/control/analytics/`

## Google registration failures

Open `/control/integrations/` to inspect each source and its sync count. Detailed source records remain in `SyncLog`; production credentials stay in environment/secret mounts. Never edit participant runtime activity in the Google Sheet.
