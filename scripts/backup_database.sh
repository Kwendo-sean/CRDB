#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[[ -f .env ]] || { echo ".env is missing" >&2; exit 1; }
set -a; . ./.env; set +a
mkdir -p backups
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
TARGET="backups/${POSTGRES_DB}_${STAMP}.dump"
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner > "$TARGET"
test -s "$TARGET"
sha256sum "$TARGET" > "${TARGET}.sha256"
find backups -type f -mtime "+${BACKUP_RETENTION_DAYS:-14}" -delete
printf 'Backup complete: %s
' "$TARGET"
