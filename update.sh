#!/usr/bin/env bash
# Pull a new version and roll it out. Mirrors the panel "Update" button.
#   ./update.sh            production (default — the live server)
#   ./update.sh --prod     same (kept for the panel watcher / old cron lines)
#   ./update.sh --dev      development compose only (runserver + Vite dev servers)
#   ./update.sh --rollback put back the images that were running before the
#                          last update (DB: restore backups/pre-update-*.sql.gz)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
[ "${1:-}" = "--dev" ] && COMPOSE="docker compose -f docker-compose.yml"
# our own images (built here); everything else is pulled by tag
APP_SERVICES="web frontend_user frontend_admin nginx"

if [ "${1:-}" = "--rollback" ]; then
  for svc in $APP_SERVICES; do
    repo=$($COMPOSE config --format json | python3 -c "import json,sys;print(json.load(sys.stdin)['services']['$svc']['image'].split(':')[0])")
    docker image inspect "$repo:rollback" >/dev/null 2>&1 || { echo "!! no $repo:rollback image"; exit 1; }
    docker tag "$repo:rollback" "$repo:latest"
    echo "   $repo:latest <- rollback"
  done
  $COMPOSE up -d --remove-orphans
  echo "==> rolled back images. Code in git is unchanged; if the update ran a migration you need to undo,"
  echo "    restore the dump: gunzip -c backups/pre-update-<…>.sql.gz | $COMPOSE exec -T db sh -c 'mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" \"\$MYSQL_DATABASE\"'"
  exit 0
fi

echo "==> current version: $(cat VERSION)"

if [ "${1:-}" != "--dev" ]; then
  stamp="$(cat VERSION)-$(date +%Y%m%d-%H%M%S)"
  echo "==> safety net: DB dump + tag running images as :rollback"
  mkdir -p "$ROOT/backups"
  $COMPOSE exec -T db sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers --no-tablespaces "$MYSQL_DATABASE"' 2>/dev/null \
    | gzip > "$ROOT/backups/pre-update-$stamp.sql.gz"
  [ "$(gunzip -c "$ROOT/backups/pre-update-$stamp.sql.gz" | head -c 100 | wc -c)" -gt 0 ] \
    || { echo "!! DB dump failed — aborting update"; exit 1; }
  chmod 600 "$ROOT/backups/pre-update-$stamp.sql.gz"
  echo "   backups/pre-update-$stamp.sql.gz"
  for svc in $APP_SERVICES; do
    cid=$($COMPOSE ps -q "$svc" 2>/dev/null || true)
    [ -n "$cid" ] || continue
    repo=$(docker inspect -f '{{.Config.Image}}' "$cid"); repo=${repo%%:*}
    docker tag "$(docker inspect -f '{{.Image}}' "$cid")" "$repo:rollback" 2>/dev/null \
      || docker tag "$repo:latest" "$repo:rollback" 2>/dev/null \
      || echo "   !! could not tag $repo:rollback (rollback for $svc = rebuild the previous git tag)"
  done
fi

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
