#!/usr/bin/env bash
# MySQL logical backup with optional gzip + simple age-based retention.
# Usage: scripts/backup.sh [output_dir]
set -euo pipefail

OUT_DIR="${1:-./backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
CONTAINER_NAME="${MYSQL_CONTAINER:-dormitory-management-system-mysql-1}"
DB_NAME="${MYSQL_DATABASE:-dms}"
DB_USER="${MYSQL_USER:-dms_user}"
DB_PASSWORD="${MYSQL_PASSWORD:?Set MYSQL_PASSWORD}"

mkdir -p "$OUT_DIR"
FILE="$OUT_DIR/${DB_NAME}_${TIMESTAMP}.sql.gz"

echo "Backing up database '$DB_NAME' from container '$CONTAINER_NAME' ..."
# --no-tablespaces: app user typically lacks PROCESS; tablespaces are unused for InnoDB logical dumps.
docker exec -e MYSQL_PWD="$DB_PASSWORD" "$CONTAINER_NAME" \
  mysqldump -u "$DB_USER" --single-transaction --routines --triggers --events \
  --no-tablespaces --set-gtid-purged=OFF "$DB_NAME" \
  | gzip >"$FILE"

echo "Backup written to $FILE"
ls -lh "$FILE"
