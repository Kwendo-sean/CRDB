#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
[[ -f .env ]] || { echo ".env is missing" >&2; exit 1; }
echo "[1/8] Fetching application updates"; git pull --ff-only
echo "[2/8] Building images"; docker compose build
echo "[3/8] Starting updated services"; docker compose up -d postgres redis web celery celery-beat
echo "[4/8] Verifying configuration"; docker compose exec -T web python manage.py check --deploy --fail-level ERROR
echo "[5/8] Applying database migrations"; docker compose exec -T web python manage.py migrate --noinput
echo "[6/8] Collecting static assets"; docker compose exec -T web python manage.py collectstatic --noinput --clear
echo "[7/8] Validating and refreshing Nginx"; docker compose exec -T nginx nginx -t; docker compose up -d nginx; docker compose exec -T nginx nginx -s reload
echo "[8/8] Verifying health"; set -a; . ./.env; set +a; curl --fail --show-error --silent "${APP_BASE_URL%/}/health/"; echo; docker compose ps
