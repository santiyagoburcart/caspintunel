#!/usr/bin/env bash
# Shared helpers for migrate-export.sh / migrate-import.sh (docs/migration.md).
# Sourced, never run. Everything works on the compose project in $ROOT; the
# end-to-end test points the same scripts at throw-away stacks through
# MIGRATE_COMPOSE / MIGRATE_BACKEND_IMAGE.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE="${MIGRATE_COMPOSE:-docker compose -f docker-compose.yml -f docker-compose.prod.yml}"
BACKEND_IMAGE="${MIGRATE_BACKEND_IMAGE:-caspintunel-backend}"
ENV_FILE="$ROOT/.env"
MIG_DIR="${MIGRATE_DIR:-$ROOT/backups/migration}"
FLAG="$ROOT/nginx/flags/maintenance"
WORKERS="bot_sales bot_backup celery_beat celery_worker"
FORMAT=1
# never restored from the old server: the new server's own database credentials
# (its MySQL volume was initialised with them), compose selection and address
KEEP_KEYS="DB_NAME DB_USER DB_PASSWORD DB_ROOT_PASSWORD DB_HOST DB_PORT COMPOSE_FILE SERVER_IP"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '    \033[1;32mok\033[0m  %s\n' "$*"; }
warn() { printf '    \033[1;33m!!\033[0m  %s\n' "$*" >&2; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

need() { for t in "$@"; do command -v "$t" >/dev/null 2>&1 || die "missing tool: $t"; done; }

# --- .env (values are never printed) -----------------------------------------
env_get() {  # env_get KEY [file]
  local v; v=$(grep -m1 "^$1=" "${2:-$ENV_FILE}" 2>/dev/null | cut -d= -f2-) || true
  v="${v%$'\r'}"; v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
  printf '%s' "$v"
}
env_set() {  # env_set KEY VALUE [file]   (replaces the line or appends it)
  local f="${3:-$ENV_FILE}" tmp; tmp="$(mktemp "$f.XXXXXX")"
  grep -v "^$1=" "$f" > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  chmod 600 "$tmp"; mv "$tmp" "$f"
}
env_del() {  # env_del KEY [file]
  local f="${2:-$ENV_FILE}" tmp; tmp="$(mktemp "$f.XXXXXX")"
  grep -v "^$1=" "$f" > "$tmp" || true
  chmod 600 "$tmp"; mv "$tmp" "$f"
}
key_hash() { printf '%s' "$(env_get "$1" "${2:-$ENV_FILE}")" | sha256sum | cut -d' ' -f1; }

# --- passphrase --------------------------------------------------------------
# MIGRATE_PASSPHRASE (env) > --passphrase-file > prompt. Exported for openssl
# (`-pass env:`), so it never shows up in the process list or a log.
load_passphrase() {  # load_passphrase <file-or-empty> <confirm:0|1>
  if [ -n "${MIGRATE_PASSPHRASE:-}" ]; then :
  elif [ -n "$1" ]; then
    [ -r "$1" ] || die "cannot read passphrase file $1"
    MIGRATE_PASSPHRASE="$(head -n1 "$1")"
  else
    [ -t 0 ] || die "no passphrase: use --passphrase-file FILE (or MIGRATE_PASSPHRASE)"
    local a b
    read -r -s -p "Archive passphrase: " a; echo
    if [ "$2" = 1 ]; then
      read -r -s -p "Repeat passphrase:  " b; echo
      [ "$a" = "$b" ] || die "passphrases differ"
    fi
    MIGRATE_PASSPHRASE="$a"
  fi
  [ "${#MIGRATE_PASSPHRASE}" -ge 12 ] || die "passphrase too short (12+ characters)"
  export MIGRATE_PASSPHRASE
}
encrypt() { openssl enc -aes-256-cbc -pbkdf2 -iter 300000 -salt -pass env:MIGRATE_PASSPHRASE; }
decrypt() { openssl enc -d -aes-256-cbc -pbkdf2 -iter 300000 -pass env:MIGRATE_PASSPHRASE; }

# --- compose / database ------------------------------------------------------
volume_name() {  # real docker volume behind a compose volume key (e.g. media_data)
  $COMPOSE config --format json | python3 -c "import json,sys;print(json.load(sys.stdin)['volumes']['$1']['name'])"
}
db_sh() { $COMPOSE exec -T db sh -c "$1"; }
db_ready() { db_sh 'mysqladmin ping -uroot -p"$MYSQL_ROOT_PASSWORD" --silent' >/dev/null 2>&1; }

table_counts() {  # "table<TAB>rows" for every base table, exact COUNT(*)
  db_sh '
    q() { mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -B "$MYSQL_DATABASE" -e "$1" 2>/dev/null; }
    for t in $(q "SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE() AND table_type=\"BASE TABLE\" ORDER BY table_name"); do
      printf "%s\t%s\n" "$t" "$(q "SELECT COUNT(*) FROM \`$t\`")"
    done'
}

# --- maintenance + worker hold -------------------------------------------------
nginx_has_flags() { $COMPOSE exec -T nginx test -d /etc/nginx/flags >/dev/null 2>&1; }
maintenance_on() {
  nginx_has_flags || die "nginx has no /etc/nginx/flags mount yet — run ./update.sh (v1.8.2+) first"
  mkdir -p "$(dirname "$FLAG")"; : > "$FLAG"
  local code
  code=$($COMPOSE exec -T nginx sh -c 'wget -S -q -O /dev/null http://127.0.0.1/ 2>&1 | grep -m1 -o "HTTP/1.1 [0-9]*" | cut -d" " -f2' || true)
  [ "$code" = 503 ] || die "maintenance flag set but nginx answered '$code' instead of 503"
  ok "maintenance mode ON (visitors get the 503 page)"
}
maintenance_off() { rm -f "$FLAG"; ok "maintenance mode OFF"; }

hold_workers() {
  env_set MIGRATION_HOLD 1
  $COMPOSE up -d --no-deps --force-recreate $WORKERS >/dev/null 2>&1 || die "could not recreate: $WORKERS"
  sleep 3; workers_held || die "bots/celery are not on hold — check: $COMPOSE logs --tail 5 $WORKERS"
  ok "bots + celery on hold (MIGRATION_HOLD=1 in .env; they stay idle across restarts and ./update.sh)"
}
workers_held() {  # every worker container must report the hold line and run no bot/celery process
  local svc cid
  for svc in $WORKERS; do
    cid=$($COMPOSE ps -q "$svc" 2>/dev/null | head -1)
    [ -n "$cid" ] || continue                       # not running at all = held
    docker logs --tail 5 "$cid" 2>&1 | grep -q "MIGRATION_HOLD=1" || return 1
  done
}
release_workers() {
  env_del MIGRATION_HOLD
  $COMPOSE up -d --no-deps --force-recreate $WORKERS >/dev/null 2>&1 || die "could not start: $WORKERS"
  ok "bots + celery started"
}

human() { numfmt --to=iec --suffix=B "$1" 2>/dev/null || echo "$1 bytes"; }
