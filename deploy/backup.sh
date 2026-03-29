#!/usr/bin/env bash
# Backup Dockerized postgres to a local file and optionally GCS.
# Usage: ./backup_docker.sh [backup_dir]
#
# Requires: docker compose in PATH, running prod profile
# Optional: gsutil for GCS upload (set GCS_BUCKET env var)

set -euo pipefail

BACKUP_DIR="${1:-$HOME/backup/yonca}"
TIMESTAMP=$(date +%F_%H-%M-%S)
BACKUP_FILE="${BACKUP_DIR}/yonca_${TIMESTAMP}.dump"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

docker compose --profile prod exec -T db \
  pg_dump -U yonca_user -Fc yonca_db > "$BACKUP_FILE"

echo "[$(date)] Backup saved to $BACKUP_FILE ($(du -sh "$BACKUP_FILE" | cut -f1))"

# Upload to GCS if bucket configured
if [ -n "${GCS_BUCKET:-}" ]; then
  gcloud storage cp "$BACKUP_FILE" "${GCS_BUCKET}/$(basename "$BACKUP_FILE")" \
    && echo "Upload succeeded" || { echo "Upload failed"; exit 1; }
  echo "[$(date)] Uploaded to ${GCS_BUCKET}"
fi

# Keep only last 7 local backups
find "$BACKUP_DIR" -name "*.dump" -type f | sort | head -n -7 | xargs -r rm -f
echo "[$(date)] Done."
