# CRDB × Predictive Analytics Lab Learning Week Experience

A self-hosted Django participation and event-operations platform for CRDB Bank's AI Impact on Banking & Skills Learning Week, 07–10 September 2026.

Google Forms remains the formal registration entry point. This application connects the resulting participant identity to one persistent QR Learning Pass, programme attendance, four official quizzes, prize standings, Learning XP, PAL AI Jobs, expo/AIoT completion, badges, analytics, and an event Control Room.

**Deploying?** Follow `GO_LIVE.md` top to bottom.

## Excel import templates

Participants, programme sessions, interactive games/expo/AIoT activities and quiz
questions are all loaded from spreadsheets. Templates are downloadable from
inside the Control Room, or generated with:

```bash
python manage.py make_templates --output ./import_templates
```

Each carries an INSTRUCTIONS sheet, the exact column names, worked example rows
and dropdown validation. Imports are all-or-nothing and report the exact row and
reason for any rejection; re-importing a corrected file updates records instead
of duplicating them.

## Custom Control Room

Normal event operation does not require Django Admin.

- Login: `/control/login/`
- Operations overview: `/control/`
- Participants: `/control/participants/`
- Programme setup: `/control/programme/sessions/`
- Experience creation: `/control/experiences/create/`
- Quiz builder: `/control/experiences/quizzes/`
- Expo/AIoT setup: `/control/experiences/activities/`
- QR scanner: `/control/scanner/`
- Scores and winners: `/control/competition/`
- Badges and XP: `/control/rewards/`
- Analytics: `/control/analytics/`
- Google Forms and PAL: `/control/integrations/`
- Event settings and audit: `/control/system/settings/`, `/control/system/audit/`

Django's `/admin/` remains only as a low-level superuser recovery interface.

## Local run

```bash
uv sync --extra dev
uv run python manage.py migrate
uv run python manage.py setup_roles
uv run python manage.py seed_demo
uv run python manage.py createsuperuser
uv run python manage.py runserver 127.0.0.1:8001
```

Open:

- Participant site: http://127.0.0.1:8001/
- Control Room: http://127.0.0.1:8001/control/
- Demo Learning Pass identity: `CRDB-DEMO`

The operational preview contains the five programme entries and four challenge names explicitly supplied in the brief. It does not invent official quiz questions.

## Official imports

Quiz workbook headers:

`day`, `challenge_name`, `question_number`, `question_text`, `answer_1` through `answer_4`, `correct_answer_number`, `time_limit`, `points`, `host_note`.

```bash
uv run python manage.py import_quizzes path/to/official-quiz.xlsx
uv run python manage.py import_sessions path/to/official-programme.xlsx
```

Competition imports are atomic and reject malformed rounds.

## Production VPS

```bash
git clone <repository>
cd <repository>
cp .env.example .env
# Set DOMAIN, SSL_EMAIL, official registration and integration values.
sudo bash server_setup.sh
```

The production stack is Docker Compose, PostgreSQL, Redis, Gunicorn/Uvicorn ASGI, Celery, Celery Beat, and Nginx. See `DEPLOYMENT.md`, `SERVER_SETUP.md`, and `BACKUP_RESTORE.md`.

## Verification

```bash
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
uv run python manage.py test
uv run python manage.py collectstatic --noinput --clear
bash -n server_setup.sh deploy.sh scripts/backup_database.sh scripts/restore_database.sh
```

## Documentation

- `ARCHITECTURE.md`
- `DATABASE_SCHEMA.md`
- `ADMIN_GUIDE.md`
- `EXPERIENCE_ENGINE.md`
- `QUIZ_ENGINE.md`
- `COMPETITION_RULES.md`
- `GOOGLE_FORMS_SYNC.md`
- `PAL_INTEGRATION.md`
- `DEPLOYMENT.md`
- `SERVER_SETUP.md`
- `BACKUP_RESTORE.md`
- `IMAGE_CREDITS.md`
