#!/usr/bin/env bash
# Ежедневный бэкап Postgres стенда. Запускается cron'ом на VPS:
#   15 3 * * * /bin/bash ~/hackaton_alfabank_2026/docker/backup.sh >> ~/backups/backup.log 2>&1
set -Eeuo pipefail

APP_DIR="$HOME/hackaton_alfabank_2026"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/postgres}"
KEEP_DAYS="${KEEP_DAYS:-14}"

cd "$APP_DIR"
mkdir -p "$BACKUP_DIR"

OUT="$BACKUP_DIR/db_$(date +%Y%m%d_%H%M%S).dump"
trap 'rm -f "$OUT.tmp"' EXIT

# Формат custom: сжатый, восстанавливается через pg_restore, в том числе выборочно
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$OUT.tmp"
mv "$OUT.tmp" "$OUT"

find "$BACKUP_DIR" -name 'db_*.dump' -mtime +"$KEEP_DAYS" -delete
echo "$(date -Is) backup ok: $OUT ($(du -h "$OUT" | cut -f1))"
