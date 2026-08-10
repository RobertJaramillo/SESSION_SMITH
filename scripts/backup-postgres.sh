#!/usr/bin/env bash
#
# backup-postgres.sh — dump the local campaign database to a timestamped file.
#
# Usage: ./scripts/backup-postgres.sh [output-dir]   (default: ./backups)
#
set -euo pipefail
cd "$(dirname "$0")/.."

OUT_DIR="${1:-backups}"
mkdir -p "$OUT_DIR"

POSTGRES_USER="${POSTGRES_USER:-campaign_app}"
POSTGRES_DB="${POSTGRES_DB:-campaign_orchestration}"

[ -n "$(docker compose ps -q db 2>/dev/null)" ] || { echo "db service is not running — start it with ./run first" >&2; exit 1; }

timestamp="$(date +%Y%m%d-%H%M%S)"
out_file="$OUT_DIR/${POSTGRES_DB}-${timestamp}.sql"

echo "Dumping '$POSTGRES_DB' to $out_file ..."
docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$out_file"
echo "Done: $out_file ($(du -h "$out_file" | cut -f1))"
