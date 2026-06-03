#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Resolve script directory to load .env from project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load environment variables if .env exists in project root
if [ -f "$PROJECT_ROOT/.env" ]; then
  # Load env vars excluding comments
  export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
fi

# Configuration parameters with fallback defaults
DB_USER=${POSTGRES_USER:-appuser}
DB_NAME=${POSTGRES_DB:-appdb}
DB_PASS=${POSTGRES_PASSWORD:-StrongPass123}
BACKUP_DIR="${PROJECT_ROOT}/backups"
DATE=$(date +%Y%m%d_%H%M%S)
FILENAME="backup_${DB_NAME}_${DATE}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "=================================================="
echo "Starting PostgreSQL backup at $(date)"
echo "Target Database: $DB_NAME"
echo "Target File: $BACKUP_DIR/$FILENAME"
echo "=================================================="

# Execute pg_dump inside container and pipe to gzip on host
if docker exec -e PGPASSWORD="$DB_PASS" postgres_db pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_DIR/$FILENAME"; then
  echo "Backup successfully created: $BACKUP_DIR/$FILENAME"
  # Secure backup file permissions (read/write by owner only)
  chmod 600 "$BACKUP_DIR/$FILENAME"
else
  echo "CRITICAL ERROR: Database backup failed!" >&2
  exit 1
fi

# Keep only the last 7 days of backups
echo "Purging backups older than 7 days..."
find "$BACKUP_DIR" -name "backup_${DB_NAME}_*.sql.gz" -mtime +7 -type f -delete

echo "Backup process finished successfully at $(date)."
echo "=================================================="