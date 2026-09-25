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
    # tag exactly what is running. Never fall back to :latest — after a manual
    # build it is already the NEW image. (containerd image store: a running
    # image whose tag moved can't be tagged any more.)
    if docker tag "$(docker inspect -f '{{.Image}}' "$cid")" "$repo:rollback" 2>/dev/null; then
      echo "   $repo:rollback = running $svc"
    else
      docker rmi "$repo:rollback" >/dev/null 2>&1 || true
      echo "   !! $svc: running image not taggable — rollback = rebuild previous tag (git worktree + docker build)"
    fi
  done
fi

if [ -d .git ]; then
  echo "==> git pull"
  git fetch --all --quiet
  git reset --hard "@{upstream}"
fi

echo "==> build"
$COMPOSE build

if [ "${1:-}" = "--dev" ]; then
  # dev: web migrates on boot (RUN_MIGRATIONS=1); no rolling deploy needed
  $COMPOSE up -d --remove-orphans
  $COMPOSE exec -T web python manage.py seed
  rm -f "$ROOT/backups/.update-requested" || true
  echo "==> now on version: $(cat VERSION)"
  exit 0
fi

# --- production: zero-downtime rollout ----------------------------------
# 1) schema + seed + static ONCE, in a one-off container of the NEW image,
#    while the old containers keep serving. Migrations must therefore stay
#    backward compatible with the previous release (add columns/tables first,
#    drop them a release later).
echo "==> migrate + seed + collectstatic (one-off container, new image)"
$COMPOSE up -d db redis >/dev/null 2>&1
$COMPOSE run --rm --no-deps -T web sh -c \
  'python manage.py migrate --noinput && python manage.py seed && python manage.py collectstatic --noinput >/dev/null'

# 2) HTTP-facing services: start the new container NEXT TO the old one, wait
#    until it is healthy (compose healthcheck), then retire the old one. nginx
#    resolves the service name at runtime and balances over both meanwhile.
ROLLING="web daphne frontend_user frontend_admin"
rollout() {
  local svc=$1 old new img hash i
  old=$($COMPOSE ps -q "$svc" | head -1)
  if [ -z "$old" ]; then $COMPOSE up -d --no-deps "$svc"; return; fi
  img=$(docker image inspect -f '{{.Id}}' "$($COMPOSE config --format json | python3 -c "import json,sys;print(json.load(sys.stdin)['services']['$svc']['image'])")")
  hash=$($COMPOSE config --hash "$svc" | awk '{print $2}')
  if [ "$(docker inspect -f '{{.Image}}' "$old")" = "$img" ] \
     && [ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.config-hash"}}' "$old")" = "$hash" ]; then
    echo "   $svc: unchanged"; return
  fi
  $COMPOSE up -d --no-deps --no-recreate --scale "$svc=2" "$svc" >/dev/null 2>&1
  new=$($COMPOSE ps -q "$svc" | grep -v "$old" | head -1)
  for i in $(seq 1 60); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$new" 2>/dev/null)" = "healthy" ] && break
    sleep 2
  done
  if [ "$(docker inspect -f '{{.State.Health.Status}}' "$new" 2>/dev/null)" != "healthy" ]; then
    echo "!! $svc: new container never became healthy — keeping the old one"
    docker logs --tail 30 "$new" 2>&1 || true
    docker rm -f "$new" >/dev/null 2>&1 || true
    exit 1
  fi
  sleep 3                       # nginx DNS cache (2s) picks up the new address
  docker stop -t 35 "$old" >/dev/null   # graceful: finishes in-flight requests
  docker rm "$old" >/dev/null
  echo "   $svc: rolled over (old ${old:0:12} -> new ${new:0:12})"
}
echo "==> rolling update: $ROLLING"
for svc in $ROLLING; do rollout "$svc"; done

# 3) everything else (celery, bots, mail, nginx image, …) — plain recreate,
#    and only where the image/config changed. Bots and beat must never run twice.
OTHERS=$($COMPOSE config --services | grep -vxE "$(echo $ROLLING | tr ' ' '|')" | tr '\n' ' ')
echo "==> up (others): $OTHERS"
$COMPOSE up -d --no-deps --remove-orphans $OTHERS

# nginx.conf is bind-mounted — reload picks up config edits without a restart
$COMPOSE exec -T nginx nginx -t >/dev/null 2>&1 && $COMPOSE exec -T nginx nginx -s reload >/dev/null 2>&1 || true

# clear the panel's update sentinel if present
rm -f "$ROOT/backups/.update-requested" || true

echo "==> now on version: $(cat VERSION)"
