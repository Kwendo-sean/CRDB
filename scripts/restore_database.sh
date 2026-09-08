#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
FILE=${1:-}
[[ -f "$FILE" ]] || { echo "Usage: CONFIRM_RESTORE=YES $0 backups/file.dump" >&2; exit 1; }
[[ "${CONFIRM_RESTORE:-}" == "YES" ]] || { echo "Refusing destructive restore. Set CONFIRM_RESTORE=YES." >&2; exit 1; }
set -a; . ./.env; set +a
[[ ! -f "${FILE}.sha256" ]] || sha256sum -c "${FILE}.sha256"
docker compose exec -T web python manage.py check
docker compose stop web celery celery-beat
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${POSTGRES_DB}' AND pid <> pg_backend_pid();"
docker compose exec -T postgres dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"
docker compose exec -T postgres createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner < "$FILE"
docker compose up -d web celery celery-beat nginx
echo "Restore complete: $FILE"
