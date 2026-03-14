#!/bin/bash
set -e

# -----------------------------
# Config
# -----------------------------
LOG_FILE="${LOG_DIR:-/var/log}/yonca_db_backup.log"
TMP_DIR="/tmp"
GCS_BUCKET="gs://yonca-main-site-db-backup"

DB_NAME="yonca_db"
DB_USER="yonca_user"
DB_SUPER="postgres"
DB_HOST="localhost"
DB_PORT="5432"

# Use .pgpass for passwordless access
export PGPASSFILE="$HOME/.pgpass"

# -----------------------------
# Logging start
# -----------------------------
echo "[$(date)] Starting PostgreSQL restore..." >> "$LOG_FILE"

# -----------------------------
# Find latest custom-format backup in GCS
# -----------------------------
LATEST_BACKUP=$(gsutil ls $GCS_BUCKET | grep '\.dump\.gz$' | sort | tail -n 1)
if [ -z "$LATEST_BACKUP" ]; then
    echo "[$(date)] ERROR: No custom-format backup found in $GCS_BUCKET" >> "$LOG_FILE"
    exit 1
fi
echo "[$(date)] Latest custom-format backup found: $LATEST_BACKUP" >> "$LOG_FILE"

# -----------------------------
# Download backup
# -----------------------------
TMP_FILE="$TMP_DIR/restore_postgres.dump.gz"
gsutil cp "$LATEST_BACKUP" "$TMP_FILE" >> "$LOG_FILE" 2>&1
echo "[$(date)] Backup downloaded: $TMP_FILE" >> "$LOG_FILE"

# -----------------------------
# Uncompress
# -----------------------------
gunzip -f "$TMP_FILE"
TMP_FILE="${TMP_FILE%.gz}"
echo "[$(date)] Backup uncompressed to $TMP_FILE" >> "$LOG_FILE"

# -----------------------------
# Drop and recreate the database as postgres
# -----------------------------
echo "[$(date)] Dropping and recreating database $DB_NAME" >> "$LOG_FILE"
psql -U "$DB_SUPER" -h "$DB_HOST" -p "$DB_PORT" -d postgres \
    -c "DROP DATABASE IF EXISTS $DB_NAME;" >> "$LOG_FILE" 2>&1
psql -U "$DB_SUPER" -h "$DB_HOST" -p "$DB_PORT" -d postgres \
    -c "CREATE DATABASE $DB_NAME OWNER $DB_SUPER;" >> "$LOG_FILE" 2>&1

# -----------------------------
# Restore the database as postgres
# -----------------------------
echo "[$(date)] Restoring database $DB_NAME from $TMP_FILE" >> "$LOG_FILE"
pg_restore -U "$DB_SUPER" -h "$DB_HOST" -p "$DB_PORT" \
    -d "$DB_NAME" --no-owner \
    "$TMP_FILE" >> "$LOG_FILE" 2>&1

# -----------------------------
# Change ownership of all objects to yonca_user
# -----------------------------
echo "[$(date)] Changing ownership of all objects to $DB_USER" >> "$LOG_FILE"
psql -U "$DB_SUPER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" <<SQL >> "$LOG_FILE" 2>&1
DO \$\$
DECLARE
    obj RECORD;
BEGIN
    -- Tables
    FOR obj IN SELECT schemaname, tablename FROM pg_tables WHERE schemaname='public' LOOP
        EXECUTE format('ALTER TABLE %I.%I OWNER TO $DB_USER;', obj.schemaname, obj.tablename);
    END LOOP;

    -- Sequences
    FOR obj IN SELECT schemaname, sequencename FROM pg_sequences WHERE schemaname='public' LOOP
        EXECUTE format('ALTER SEQUENCE %I.%I OWNER TO $DB_USER;', obj.schemaname, obj.sequencename);
    END LOOP;

    -- Views
    FOR obj IN SELECT schemaname, viewname FROM pg_views WHERE schemaname='public' LOOP
        EXECUTE format('ALTER VIEW %I.%I OWNER TO $DB_USER;', obj.schemaname, obj.viewname);
    END LOOP;
END
\$\$;
SQL

echo "[$(date)] PostgreSQL restore completed successfully" >> "$LOG_FILE"

# -----------------------------
# Cleanup
# -----------------------------
rm -f "$TMP_FILE"
echo "[$(date)] Temporary files removed" >> "$LOG_FILE"
