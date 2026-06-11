#!/usr/bin/env bash
# Restore Dockerized postgres from a backup file.
# Usage: ./restore_docker.sh <backup_file>
#
# Supports both .dump (custom format) and .sql (plain) files.
# WARNING: destroys existing data.

set -euo pipefail

BACKUP_FILE="${1:?Usage: $0 <backup_file>}"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Error: file not found: $BACKUP_FILE"
  exit 1
fi

echo "[$(date)] Restoring from $BACKUP_FILE..."
read -r -p "This will OVERWRITE the current database. Continue? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 1; }

case "$BACKUP_FILE" in
  *.dump)
    docker compose exec -T db \
      pg_restore -U yonca_user -d yonca_db --clean --if-exists --no-owner --no-acl \
      < "$BACKUP_FILE"
    ;;
  *.sql)
    docker compose exec -T db \
      psql -U yonca_user -d yonca_db \
      < "$BACKUP_FILE"
    ;;
  *)
    echo "Error: unsupported file format (expected .dump or .sql)"
    exit 1
    ;;
esac

echo "[$(date)] Restore complete."
