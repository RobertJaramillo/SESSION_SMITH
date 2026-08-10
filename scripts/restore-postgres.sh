#!/usr/bin/env bash
#
# restore-postgres.sh — restore a dump produced by backup-postgres.sh.
# This REPLACES the current contents of the database.
#
# Usage: ./scripts/restore-postgres.sh path/to/dump.sql
#
set -euo pipefail
cd "$(dirname "$0")/.."

dump_file="${1:-}"
[ -n "$dump_file" ] || { echo "usage: $0 <dump-file>" >&2; exit 1; }
[ -f "$dump_file" ] || { echo "no such file: $dump_file" >&2; exit 1; }

POSTGRES_USER="${POSTGRES_USER:-campaign_app}"
POSTGRES_DB="${POSTGRES_DB:-campaign_orchestration}"

[ -n "$(docker compose ps -q db 2>/dev/null)" ] || { echo "db service is not running — start it with ./run first" >&2; exit 1; }

echo "This will REPLACE all current data in '$POSTGRES_DB' with the contents of $dump_file."
read -rp "Continue? [y/N] " confirm
case "$confirm" in
  y|Y) ;;
  *) echo "Aborted."; exit 1 ;;
esac

echo "Dropping and recreating '$POSTGRES_DB' ..."
docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\";"
docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\";"

echo "Restoring from $dump_file ..."
docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$dump_file"
echo "Restore complete."
