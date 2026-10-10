#!/usr/bin/env bash
set -e

# Server migration: with MIGRATION_HOLD=1 in .env the bots and celery stay idle
# (container up, nothing running), so the same bot never polls from two servers
# and no task touches the DB mid-copy. Survives restarts and ./update.sh.
# Set / cleared by scripts/migrate-export.sh --final|--resume and
# scripts/migrate-import.sh [--start-workers]  (docs/migration.md).
if [ "${MIGRATION_HOLD:-0}" = "1" ]; then
  case " $* " in
    *" run_sales_bot "*|*" run_backup_bot "*|*" celery "*)
      echo "[entrypoint] MIGRATION_HOLD=1 — '$*' is on hold (not started). See docs/migration.md"
      trap 'exit 0' TERM INT
      while :; do sleep 3600 & wait $!; done ;;
  esac
fi

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-3306}"

echo "[entrypoint] waiting for database ${DB_HOST}:${DB_PORT} ..."
until nc -z "$DB_HOST" "$DB_PORT"; do
  sleep 1
done
echo "[entrypoint] database is up"

# Only the web/worker containers should run migrations; guard with RUN_MIGRATIONS.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "[entrypoint] applying migrations"
  python manage.py migrate --noinput
fi

if [ "${COLLECT_STATIC:-0}" = "1" ]; then
  echo "[entrypoint] collecting static"
  python manage.py collectstatic --noinput
fi

if [ "${SEED:-0}" = "1" ]; then
  echo "[entrypoint] seeding initial data (idempotent)"
  python manage.py seed
fi

exec "$@"
