#!/usr/bin/env bash
# Restore a gzipped MySQL logical backup.
# Usage: scripts/restore.sh <backup_file.sql.gz> [target_db]
#   target_db defaults to MYSQL_DATABASE (production). For drills, pass an
#   isolated database name (e.g. dms_restore_test) — never overwrite live data
#   without an explicit maintenance window.
set -euo pipefail

FILE="${1:?Usage: scripts/restore.sh <backup_file.sql.gz> [target_db]}"
TARGET_DB="${2:-${MYSQL_DATABASE:-dms}}"
CONTAINER_NAME="${MYSQL_CONTAINER:-dormitory-management-system-mysql-1}"
DB_USER="${MYSQL_USER:-dms_user}"
DB_PASSWORD="${MYSQL_PASSWORD:?Set MYSQL_PASSWORD}"
ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-}"

if [[ ! -f "$FILE" ]]; then
  echo "Backup file not found: $FILE" >&2
  exit 1
fi

echo "Restoring '$FILE' into database '$TARGET_DB' ..."
if [[ -n "$ROOT_PASSWORD" ]]; then
  docker exec -e MYSQL_PWD="$ROOT_PASSWORD" "$CONTAINER_NAME" \
    mysql -u root -e "CREATE DATABASE IF NOT EXISTS \`$TARGET_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
  # Grant app user access when restoring into a non-default drill database.
  docker exec -e MYSQL_PWD="$ROOT_PASSWORD" "$CONTAINER_NAME" \
    mysql -u root -e "GRANT ALL PRIVILEGES ON \`$TARGET_DB\`.* TO '$DB_USER'@'%'; FLUSH PRIVILEGES;"
fi

gunzip -c "$FILE" | docker exec -i -e MYSQL_PWD="$DB_PASSWORD" "$CONTAINER_NAME" \
  mysql -u "$DB_USER" "$TARGET_DB"

echo "Restore completed into '$TARGET_DB'. Verify data before switching traffic."
