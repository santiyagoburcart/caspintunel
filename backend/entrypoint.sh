#!/usr/bin/env bash
set -e

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
