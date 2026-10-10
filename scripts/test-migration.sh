#!/usr/bin/env bash
# End-to-end test of the migration toolkit on two THROW-AWAY stacks.
#
#   ./scripts/test-migration.sh            (needs the caspintunel-backend / -nginx images; ~3 min)
#
# "old server" = compose project migtest-src, "new server" = migtest-dst: each a
# copy of this working tree in a temp dir with its own .env (different keys and
# DB passwords), its own network, volumes and no published ports. Nothing here
# can reach the live stack: the project name is rewritten in the copies and
# checked before anything starts. Flow:
#   fake data → test export → import → compare → more data → FINAL export
#   (maintenance + hold) → import again → compare exactly → start workers on dst.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d "${MIGTEST_DIR:-${TMPDIR:-/tmp}}/caspin-migtest-XXXXXX")"
PASS_FILE="$T/passphrase"; head -c 24 /dev/urandom | base64 > "$PASS_FILE"; chmod 600 "$PASS_FILE"
FAILS=0
step() { printf '\n\033[1;35m### %s\033[0m\n' "$*"; }
check() { if eval "$2"; then printf '  \033[1;32mPASS\033[0m  %s\n' "$1"; else printf '  \033[1;31mFAIL\033[0m  %s\n' "$1"; FAILS=$((FAILS + 1)); fi; }
rnd() { head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "${1:-32}"; }

compose_of() { echo "docker compose -p migtest-$1 --project-directory $T/$1 -f $T/$1/docker-compose.yml -f $T/$1/docker-compose.prod.yml -f $T/$1/docker-compose.migtest.yml"; }
run() { local side=$1; shift; ( cd "$T/$side" && MIGRATE_COMPOSE="$(compose_of "$side")" MIGRATE_SAME_HOST_OK="${SAME_HOST_OK-1}" "$@" ); }

cleanup() {
  for side in src dst; do
    [ -d "$T/$side" ] && $(compose_of "$side") down -v --remove-orphans >/dev/null 2>&1 || true
  done
  # root-owned files written by containers (backups, media mounts)
  docker run --rm --network none -v "$T:/t" --entrypoint sh caspintunel-backend -c 'rm -rf /t/src /t/dst' >/dev/null 2>&1 || true
  rm -rf "$T"
}
trap cleanup EXIT

make_server() {  # make_server src|dst
  local side=$1 dir="$T/$1"
  mkdir -p "$dir"
  ( cd "$ROOT" && git ls-files -co --exclude-standard -z | tar --null -T - -cf - ) | tar -xf - -C "$dir"
  sed -i "s/^name: caspintunel$/name: migtest-$side/" "$dir/docker-compose.yml"
  cat > "$dir/docker-compose.migtest.yml" <<'YML'
# throw-away stack: nothing published on the host, nothing built; the backend
# containers run THIS working tree (entrypoint included), not the baked image
x-code: &code
  volumes:
    - ./backend:/app
services:
  web: *code
  daphne: *code
  celery_worker: *code
  celery_beat: *code
  bot_sales: *code
  bot_backup: *code
  nginx:
    ports: !reset []
  mailserver:
    ports: !reset []
  frontend_user:
    ports: !reset []
  frontend_admin:
    ports: !reset []
YML
  cat > "$dir/.env" <<ENV
DOMAIN=migtest.example
SERVER_IP=192.0.2.$([ "$side" = src ] && echo 10 || echo 20)
DJANGO_SETTINGS_MODULE=config.settings.prod
SECRET_KEY=$(rnd 50)
DEBUG=false
ALLOWED_HOSTS=migtest.example,localhost,127.0.0.1,web
PUBLIC_BASE_URL=https://migtest.example
FIELD_ENCRYPTION_KEY=$(head -c 32 /dev/urandom | base64 | tr '+/' '-_')
DB_NAME=caspintunel
DB_USER=caspintunel
DB_PASSWORD=$(rnd 24)
DB_ROOT_PASSWORD=$(rnd 24)
DB_HOST=db
DB_PORT=3306
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
PANEL_SYNC_ENABLED=false
EMAIL_HOST=mailserver
EMAIL_PORT=25
MARKER=$side
ENV
  chmod 600 "$dir/.env"
  local C; C="$(compose_of "$side")"
  [ "$($C config --format json | python3 -c 'import json,sys;print(json.load(sys.stdin)["name"])')" = "migtest-$side" ] \
    || { echo "refusing to continue: compose project is not migtest-$side"; exit 1; }
  $C up -d db redis >/dev/null 2>&1
  for i in $(seq 1 60); do $C exec -T db sh -c 'mysqladmin ping -uroot -p"$MYSQL_ROOT_PASSWORD" --silent' >/dev/null 2>&1 && break; sleep 2; done
  sleep 3
  $C run --rm --no-deps -T web sh -c 'python manage.py migrate --noinput >/dev/null && python manage.py seed >/dev/null && python manage.py collectstatic --noinput >/dev/null'
  $C up -d --no-deps web daphne bot_sales bot_backup celery_beat celery_worker nginx >/dev/null 2>&1
  for i in $(seq 1 60); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$($C ps -q web | head -1)" 2>/dev/null)" = healthy ] && return 0; sleep 2
  done
  echo "web of migtest-$side never became healthy"; $C logs --tail 20 web; exit 1
}

fake_data() {  # fake_data <tag> <n-users>
  local out
  out=$($(compose_of src) exec -T web python manage.py shell -c "
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from apps.accounts.models import User
from apps.orders.models import Order
from apps.panel.models import Panel
from apps.plans.models import Plan
from apps.telegram.models import TelegramConfig
tag, n = '$1', $2
panel, _ = Panel.objects.get_or_create(name='migtest', defaults=dict(base_url='https://panel.invalid', admin_username='adm', admin_password_enc='panel-secret-123', is_active=False))
TelegramConfig.objects.update_or_create(bot_type='sales', defaults=dict(token='123456:fake-bot-token', is_active=False))
plan, _ = Plan.objects.get_or_create(name_fa='پلن آزمایشی', defaults=dict(panel=panel, price=Decimal('250000'), data_limit=1024**3, duration_days=30))
for i in range(n):
    u = User.objects.create_user(f'{tag}-user{i}', 'Str0ngPass!')
    Order.objects.create(user=u, plan=plan, amount=250000, amount_unique=250000 + i, status='completed', unique_expire_at=timezone.now() + timedelta(minutes=30))
print('fake data', tag, User.objects.count(), Order.objects.count())
" 2>&1) || true
  echo "$out" | grep "fake data" || { echo "$out"; return 1; }
  $(compose_of src) exec -T web sh -c "mkdir -p /app/media/receipts/$1 /app/media/branding && for i in 1 2 3; do head -c 2048 /dev/urandom > /app/media/receipts/$1/r\$i.jpg; done && echo logo-$1 > /app/media/branding/logo-$1.svg"
}

secret_of() { $(compose_of "$1") exec -T web python manage.py shell -c "
from apps.panel.models import Panel
from apps.telegram.models import TelegramConfig
print('SECRETS', Panel.objects.get(name='migtest').admin_password_enc, TelegramConfig.objects.get(bot_type='sales').token)" 2>&1 | grep SECRETS; }
counts_of() { run "$1" bash -c '. scripts/migrate-lib.sh; table_counts' | tr '\n\t' ' ='; }   # every table, exact
users_of() { counts_of "$1" | tr ' ' '\n' | grep '^user=' | cut -d= -f2; }
core_of() { counts_of "$1" | tr ' ' '\n' | grep -E '^(user|order|plan|panel|telegram_config|site_config)=' | tr '\n' ' '; }
media_sum() { docker run --rm --network none -v "migtest-$1_media_data:/m:ro" --entrypoint sh caspintunel-backend -c 'cd /m && find . -type f -print0 | sort -z | xargs -0 -r sha256sum | sha256sum' | cut -d' ' -f1; }
http() { $(compose_of "$1") exec -T nginx sh -c "wget -S -q -O /dev/null --header 'X-Forwarded-Proto: https' http://127.0.0.1$2 2>&1 | grep -m1 -o 'HTTP/1.1 [0-9]*' | cut -d' ' -f2"; }
held() { $(compose_of "$1") logs --tail 3 bot_sales 2>&1 | grep -q "MIGRATION_HOLD=1"; }
archive() { ls -t "$T/src/backups/migration/"*$1.tar.enc 2>/dev/null | head -1; }   # $1 is a glob

step "1. two throw-away servers"
make_server src; make_server dst
check "projects are isolated (migtest-src / migtest-dst)" '[ "$(docker ps --filter name=migtest- -q | wc -l)" -ge 10 ]'
check "the two servers have DIFFERENT keys and DB passwords" '! diff -q <(grep -E "^(SECRET_KEY|FIELD_ENCRYPTION_KEY|DB_PASSWORD)=" "$T/src/.env") <(grep -E "^(SECRET_KEY|FIELD_ENCRYPTION_KEY|DB_PASSWORD)=" "$T/dst/.env") >/dev/null'

step "2. fake data on the old server"
fake_data first 12
mkdir -p "$T/src/mail/config/opendkim/keys/migtest.example" && echo "fake-dkim-private-key" > "$T/src/mail/config/opendkim/keys/migtest.example/mail.private"
SRC_SECRET="$(secret_of src)"
check "source holds encrypted secrets" '[ -n "$SRC_SECRET" ]'

step "3. test export (site stays up)"
run src ./scripts/migrate-export.sh --passphrase-file "$PASS_FILE" > "$T/export1.log" 2>&1 || { cat "$T/export1.log"; exit 1; }
tail -n 16 "$T/export1.log"
A1="$(archive '[0-9]')"
check "archive + .sha256 written, mode 600" '[ -s "$A1" ] && [ -s "$A1.sha256" ] && [ "$(stat -c %a "$A1")" = 600 ]'
check "archive is encrypted (no plain SQL / env inside)" '! grep -qa -e "CREATE TABLE" -e "SECRET_KEY" "$A1"'
check "old site still open after a plain export" '[ "$(http src /api/v1/health/)" != 503 ]'
check "plain export left bots running (no hold)" '! held src'

step "4. guards"
mkdir -p "$T/dst/backups/migration"; cp "$A1" "$A1.sha256" "$T/dst/backups/migration/"
D1="$T/dst/backups/migration/$(basename "$A1")"
echo "wrong-passphrase-123456" > "$T/wrong"
check "wrong passphrase is refused" '! run dst ./scripts/migrate-import.sh "$D1" --passphrase-file "$T/wrong" --yes >/dev/null 2>&1'
cp "$D1" "$T/corrupt.tar.enc"; cp "$D1.sha256" "$T/corrupt.tar.enc.sha256"; printf 'X' | dd of="$T/corrupt.tar.enc" bs=1 seek=4096 conv=notrunc 2>/dev/null
sed -i "s/$(basename "$D1")/corrupt.tar.enc/" "$T/corrupt.tar.enc.sha256"
check "damaged archive is refused" '! run dst ./scripts/migrate-import.sh "$T/corrupt.tar.enc" --passphrase-file "$PASS_FILE" --yes >/dev/null 2>&1'
check "import on the machine that made the archive is refused" '! SAME_HOST_OK= run dst ./scripts/migrate-import.sh "$D1" --passphrase-file "$PASS_FILE" --yes >/dev/null 2>&1'
check "refused imports changed nothing (dst still has its own key)" '[ "$(grep ^MARKER= "$T/dst/.env")" = MARKER=dst ]'

step "5. import the test copy into the new server"
DST_DB_PW="$(grep '^DB_PASSWORD=' "$T/dst/.env")"
run dst ./scripts/migrate-import.sh "$D1" --passphrase-file "$PASS_FILE" --yes > "$T/import1.log" 2>&1 || { cat "$T/import1.log"; exit 1; }
cat "$T/import1.log"
# the old server is LIVE here (celery writes health rows), so only the business tables must be equal;
# the final export below is compared table by table
check "business tables equal (users, orders, plans, panels, bot + site config)" '[ -n "$(core_of src)" ] && [ "$(core_of src)" = "$(core_of dst)" ]'
check "import compared every table with the manifest" 'grep -q -e "row counts match the manifest in every table" -e "this was a test copy of a LIVE site" "$T/import1.log"'
USERS1="$(users_of dst)"; echo "    users after the test copy: $USERS1 ($(counts_of dst | wc -w) tables)"
check "media identical (sha256 of every file)" '[ "$(media_sum src)" = "$(media_sum dst)" ]'
check "same SECRET_KEY + FIELD_ENCRYPTION_KEY as the old server" 'diff -q <(grep -E "^(SECRET_KEY|FIELD_ENCRYPTION_KEY)=" "$T/src/.env") <(grep -E "^(SECRET_KEY|FIELD_ENCRYPTION_KEY)=" "$T/dst/.env") >/dev/null'
check "new server kept its OWN database password and IP" '[ "$(grep "^DB_PASSWORD=" "$T/dst/.env")" = "$DST_DB_PW" ] && grep -q "^SERVER_IP=192.0.2.20$" "$T/dst/.env"'
check "other settings came from the old server" 'grep -q "^MARKER=src$" "$T/dst/.env"'
check "encrypted values decrypt to the same secrets" '[ "$(secret_of dst)" = "$SRC_SECRET" ]'
check "DKIM key carried over" '[ "$(cat "$T/dst/mail/config/opendkim/keys/migtest.example/mail.private")" = fake-dkim-private-key ]'
check "bots + celery on hold on the new server" 'held dst && grep -q "^MIGRATION_HOLD=1$" "$T/dst/.env"'
check "new server serves requests (maintenance off, API up)" '[ "$(http dst /api/v1/health/)" = 200 ]'
check "pre-import state kept (before-import-*/env, db.sql.gz)" 'ls "$T"/dst/backups/migration/before-import-*/db.sql.gz >/dev/null && ls "$T"/dst/backups/migration/before-import-*/env >/dev/null'
$(compose_of dst) restart bot_sales >/dev/null 2>&1; sleep 4
check "hold survives a container restart" 'held dst'

step "6. more activity on the old server, then the FINAL export"
fake_data second 5
run src ./scripts/migrate-export.sh --final --yes --passphrase-file "$PASS_FILE" > "$T/export2.log" 2>&1 || { cat "$T/export2.log"; exit 1; }
tail -n 20 "$T/export2.log"
A2="$(archive -final)"
check "old site in maintenance: / and API answer 503" '[ "$(http src /)" = 503 ] && [ "$(http src /api/v1/orders/)" = 503 ]'
check "ACME challenge path still open in maintenance" '[ "$(http src /.well-known/acme-challenge/x)" = 404 ]'
check "old server's bots + celery on hold" 'held src && grep -q "^MIGRATION_HOLD=1$" "$T/src/.env"'
check "exported .env carries no hold flag of its own" '! run src sh -c "MIGRATE_PASSPHRASE=\$(cat $PASS_FILE) openssl enc -d -aes-256-cbc -pbkdf2 -iter 300000 -pass env:MIGRATE_PASSPHRASE < $A2 | tar -xOf - ./env" | grep -q MIGRATION_HOLD'

step "7. import the FINAL archive (replaces the test copy)"
cp "$A2" "$A2.sha256" "$T/dst/backups/migration/"
run dst ./scripts/migrate-import.sh "$T/dst/backups/migration/$(basename "$A2")" --passphrase-file "$PASS_FILE" --yes > "$T/import2.log" 2>&1 || { cat "$T/import2.log"; exit 1; }
grep -E "ok|!!|rows|FINAL" "$T/import2.log"
check "import reports an exact row-count match" 'grep -q "row counts match the manifest in every table" "$T/import2.log"'
echo "    users old/new: $(users_of src) / $(users_of dst)"
check "row counts equal in every table after the final import" '[ -n "$(counts_of src)" ] && [ "$(counts_of src)" = "$(counts_of dst)" ]'
check "the 5 users added after the test copy arrived" '[ "$(users_of dst)" = "$((USERS1 + 5))" ]'
check "media identical after the final import" '[ "$(media_sum src)" = "$(media_sum dst)" ]'
check "still on hold after the final import" 'held dst'

step "8. go live on the new server, old one stays parked"
run dst ./scripts/migrate-import.sh --start-workers --yes > "$T/start.log" 2>&1 || { cat "$T/start.log"; exit 1; }
sleep 6
check "new server: hold released, bot process started" '! grep -q "^MIGRATION_HOLD=" "$T/dst/.env" && ! held dst'
check "old server: still in maintenance and on hold" '[ "$(http src /)" = 503 ] && held src'

step "9. rollback path: resume the old server"
run src ./scripts/migrate-export.sh --resume --yes > "$T/resume.log" 2>&1 || { cat "$T/resume.log"; exit 1; }
sleep 6
check "old server reopened and bots running again" '[ "$(http src /api/v1/health/)" = 200 ] && ! held src && ! grep -q "^MIGRATION_HOLD=" "$T/src/.env"'

echo
if [ "$FAILS" = 0 ]; then echo "migration toolkit: ALL CHECKS PASSED"; else echo "migration toolkit: $FAILS CHECK(S) FAILED"; exit 1; fi
