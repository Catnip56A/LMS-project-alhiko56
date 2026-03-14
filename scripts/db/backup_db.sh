#!/bin/bash
set -e

# -----------------------------
# Config
# -----------------------------
LOG_FILE="${LOG_DIR:-/var/log}/yonca_db_backup.log"
TMP_BACKUP="/tmp/yonca_db_backup_$(date +%F_%H-%M-%S).dump"
GCS_PATH="gs://yonca-main-site-db-backup/yonca_db_backup_$(date +%F_%H-%M-%S).dump.gz"

DB_NAME="yonca_db"
DB_USER="yonca_user"
DB_HOST="localhost"
DB_PORT="5432"

# Use .pgpass for password
export PGPASSFILE="$HOME/.pgpass"

echo "[$(date)] Starting PostgreSQL backup..." >> "$LOG_FILE"

# -----------------------------
# Create PostgreSQL backup
# -----------------------------
pg_dump -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -F c -b -v -f "$TMP_BACKUP" "$DB_NAME" >> "$LOG_FILE" 2>&1

# Check backup file is not empty
if [ ! -s "$TMP_BACKUP" ]; then
  echo "[$(date)] ERROR: Backup file is empty!" >> "$LOG_FILE"
  exit 1
fi

# Compress the backup
gzip -f "$TMP_BACKUP"

# Upload to Google Cloud
gsutil cp "${TMP_BACKUP}.gz" "$GCS_PATH" >> "$LOG_FILE" 2>&1

echo "[$(date)] PostgreSQL backup completed successfully" >> "$LOG_FILE"
