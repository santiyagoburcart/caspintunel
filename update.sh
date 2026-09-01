#!/usr/bin/env bash
# Pull a new version and roll it out. Mirrors the panel "Update" button.
#   ./update.sh            dev
#   ./update.sh --prod     production compose
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

COMPOSE="docker compose -f docker-compose.yml"
[ "${1:-}" = "--prod" ] && COMPOSE="$COMPOSE -f docker-compose.prod.yml"

echo "==> current version: $(cat VERSION)"

if [ -d .git ]; then
  echo "==> git pull"
  git fetch --all --quiet
  git reset --hard "@{upstream}"
fi

echo "==> build"
$COMPOSE build

echo "==> up"
$COMPOSE up -d --remove-orphans

echo "==> migrate + seed (idempotent — picks up new settings / beat tasks)"
$COMPOSE exec -T web python manage.py migrate --noinput
$COMPOSE exec -T web python manage.py seed

echo "==> collectstatic"
$COMPOSE exec -T web python manage.py collectstatic --noinput || true

# clear the panel's update sentinel if present
rm -f "$ROOT/backups/.update-requested" || true

echo "==> now on version: $(cat VERSION)"
