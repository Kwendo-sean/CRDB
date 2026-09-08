# Backup and restore

Competition and attendance data require recoverable PostgreSQL backups.

## Automated backup

`server_setup.sh` installs a daily 02:15 UTC cron entry for `scripts/backup_database.sh`. The script creates a custom-format PostgreSQL dump and SHA-256 checksum under `backups/`, then removes files older than `BACKUP_RETENTION_DAYS`.

Run manually:

```bash
./scripts/backup_database.sh
```

Copy backups off the VPS to encrypted external storage. A backup remaining only on the application VPS is not disaster recovery.

## Restore

Restoration replaces the configured database and temporarily stops application workers:

```bash
CONFIRM_RESTORE=YES ./scripts/restore_database.sh backups/crdb_learning_week_TIMESTAMP.dump
```

The script validates the checksum when present, stops web/worker/beat, terminates database sessions, recreates the database, restores without ownership metadata, and starts services.

## Rehearsal

Before Learning Week, restore the latest backup into a disposable VPS, then verify participant count, attendance, quiz responses, score totals, winner statuses, `/health/`, and Control Room authentication. Record actual recovery time and repeat after schema changes.
