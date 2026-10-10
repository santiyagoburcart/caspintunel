#!/usr/bin/env bash
# Server migration, step 2 — run on the NEW server, after a fresh install of the
# SAME version.  Runbook: docs/migration.md
#
#   ./scripts/migrate-import.sh ARCHIVE.tar.enc    verify + restore; bots/celery stay ON HOLD
#   ./scripts/migrate-import.sh --start-workers    after DNS points here and the OLD server's
#                                                  bots are stopped: start bots + celery
#   ./scripts/migrate-import.sh --status           what is running / on hold
#
#   --passphrase-file FILE     read the archive passphrase from FILE (else: prompt / MIGRATE_PASSPHRASE)
#   --no-tls                   do not restore the TLS certificates from the archive
#   --allow-version-mismatch   import although VERSION here differs from the archive
#   --yes                      no confirmation question
#
# Restores the database, the media volume, .env (same SECRET_KEY and
# FIELD_ENCRYPTION_KEY; this server keeps its own DB credentials), mail config
# and TLS, runs migrations, and compares every table's row count and every media
# file's checksum with the manifest. It can be repeated: a later archive (the
# final one) simply replaces the test copy.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/migrate-lib.sh"

MODE=import; YES=0; TLS=1; PASSFILE=""; ARCHIVE=""; ANYVER=0
while [ $# -gt 0 ]; do
  case "$1" in
    --start-workers) MODE=start ;;
    --status) MODE=status ;;
    --yes) YES=1 ;;
    --no-tls) TLS=0 ;;
    --allow-version-mismatch) ANYVER=1 ;;
    --passphrase-file) PASSFILE="${2:?}"; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    -*) die "unknown option: $1" ;;
    *) ARCHIVE="$1" ;;
  esac; shift
done

need docker openssl tar gzip sha256sum python3
[ -f "$ENV_FILE" ] || die "no .env here — install the same version first (./install.sh)"

status() {
  echo "    version here     : $(cat VERSION)"
  echo "    maintenance mode : $([ -e "$FLAG" ] && echo ON || echo off)"
  echo "    MIGRATION_HOLD   : $([ "$(env_get MIGRATION_HOLD)" = 1 ] && echo '1 (bots + celery idle)' || echo 'not set (bots + celery run)')"
  $COMPOSE ps --format '{{.Service}}: {{.Status}}' 2>/dev/null | sort | sed 's/^/      /' 
}

if [ "$MODE" = status ]; then status; exit 0; fi

if [ "$MODE" = start ]; then
  say "Start bots + celery on THIS server"
  echo "    Do this only when ALL of these are true:"
  echo "      1. the final archive was imported here and the counts matched,"
  echo "      2. on the OLD server bots/celery are on hold (migrate-export.sh --final did that)"
  echo "         or the old server is powered off,"
  echo "      3. DNS already points to this server."
  echo "    Two servers polling the same Telegram bot lose messages and can deliver twice."
  if [ "$YES" != 1 ]; then read -r -p "    type START to continue: " a; [ "$a" = START ] || die "aborted"; fi
  release_workers
  sleep 5
  $COMPOSE logs --tail 4 $WORKERS 2>&1 | sed 's/^/    /' || true
  exit 0
fi

# ---------------------------------------------------------------- import
[ -n "$ARCHIVE" ] && [ -f "$ARCHIVE" ] || die "usage: $0 ARCHIVE.tar.enc   (file not found: '${ARCHIVE:-}')"
db_ready || die "the database container is not running/healthy — finish the fresh install first"

say "Verify the archive"
if [ -f "$ARCHIVE.sha256" ]; then
  [ "$(cut -d' ' -f1 "$ARCHIVE.sha256")" = "$(sha256sum "$ARCHIVE" | cut -d' ' -f1)" ] \
    || die "the archive does not match its .sha256 — it was damaged in transfer, copy it again"
  ok "transfer checksum (.sha256)"
else
  warn "no $ARCHIVE.sha256 next to the archive — transfer not verified (inner checksums still are)"
fi
load_passphrase "$PASSFILE" 0
mkdir -p "$MIG_DIR"; chmod 700 "$MIG_DIR"
WORK="$(mktemp -d "$MIG_DIR/.import-XXXXXX")"; chmod 700 "$WORK"
trap 'rm -rf "$WORK"' EXIT
decrypt < "$ARCHIVE" 2>/dev/null | tar -xf - -C "$WORK" 2>/dev/null || die "cannot decrypt — wrong passphrase or damaged archive"
[ -f "$WORK/manifest.json" ] || die "no manifest.json in the archive"

python3 - "$WORK" "$FORMAT" <<'PY' || die "manifest check failed"
import hashlib, json, os, sys
work, fmt = sys.argv[1], int(sys.argv[2])
m = json.load(open(os.path.join(work, "manifest.json")))
if m.get("format") != fmt:
    sys.exit(f"archive format {m.get('format')} != {fmt} — use the scripts of the same release on both servers")
bad = 0
for name, meta in m["files"].items():
    p = os.path.join(work, name)
    if not os.path.exists(p):
        print("    missing:", name); bad += 1; continue
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != meta["sha256"] or os.path.getsize(p) != meta["size"]:
        print("    checksum mismatch:", name); bad += 1
extra = set(os.listdir(work)) - set(m["files"]) - {"manifest.json"}
if extra:
    print("    not in the manifest:", sorted(extra)); bad += 1
sys.exit(1 if bad else 0)
PY
mf() { python3 -c "import json,sys;m=json.load(open('$WORK/manifest.json'));print($1)"; }
ok "every part matches the manifest ($(mf 'len(m["files"])') files)"
A_VERSION="$(mf 'm["version"]')"; A_FINAL="$(mf 'm["final"]')"; A_HOST="$(mf 'm["source_host"]')"; A_DOMAIN="$(mf 'm["domain"]')"
echo "    from     : $A_HOST ($A_DOMAIN), created $(mf 'm["created_at"]')"
echo "    version  : $A_VERSION ($(mf 'm["commit"][:10]'))"
echo "    kind     : $([ "$A_FINAL" = True ] && echo 'FINAL export (site was in maintenance)' || echo 'test copy (site was live while exporting)')"
echo "    contents : $(mf 'len(m["database"]["tables"])') tables / $(mf 'm["database"]["total_rows"]') rows, $(mf 'm["media"]["files"]') media files"

[ "$A_VERSION" = "$(cat VERSION)" ] || [ "$ANYVER" = 1 ] \
  || die "version here is $(cat VERSION), archive is $A_VERSION — check out v$A_VERSION here (or --allow-version-mismatch)"
[ "$A_HOST" != "$(hostname)" ] || [ -n "${MIGRATE_SAME_HOST_OK:-}" ] \
  || die "this archive was made ON THIS machine ($A_HOST) — the import belongs on the NEW server"

say "This REPLACES the database, media files, .env and mail config of THIS server ($(hostname))"
if [ "$YES" != 1 ]; then read -r -p "    type the domain ($A_DOMAIN) to continue: " a; [ "$a" = "$A_DOMAIN" ] || die "aborted"; fi

STAMP="$(date -u +%Y%m%d-%H%M%S)"
SAFE="$MIG_DIR/before-import-$STAMP"; mkdir -p "$SAFE"; chmod 700 "$SAFE"

say "Quiesce this server"
if nginx_has_flags; then mkdir -p "$(dirname "$FLAG")"; : > "$FLAG"; ok "maintenance mode ON during the import"; fi
env_set MIGRATION_HOLD 1
$COMPOSE stop web daphne $WORKERS >/dev/null 2>&1 || true
ok "web, daphne, bots, celery stopped"

say "Safety copies of what is here now → ${SAFE#$ROOT/}"
cp -p "$ENV_FILE" "$SAFE/env"
db_sh 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers --no-tablespaces "$MYSQL_DATABASE"' 2>/dev/null | gzip > "$SAFE/db.sql.gz"
[ -d "$ROOT/mail/config" ] && tar -C "$ROOT" -cf "$SAFE/mail-config.tar" mail/config
ok "current .env, database dump, mail config"

say ".env — the old server's settings and keys, this server's database credentials"
NEW_ENV="$WORK/env.merged"; cp "$WORK/env" "$NEW_ENV"; chmod 600 "$NEW_ENV"
for k in $KEEP_KEYS; do
  if grep -q "^$k=" "$ENV_FILE"; then env_set "$k" "$(grep -m1 "^$k=" "$ENV_FILE" | cut -d= -f2-)" "$NEW_ENV"; fi
done
env_set MIGRATION_HOLD 1 "$NEW_ENV"
for k in SECRET_KEY FIELD_ENCRYPTION_KEY; do
  [ "$(key_hash "$k" "$NEW_ENV")" = "$(mf "m['keys']['$k']")" ] || die "$k in the restored .env is not the old server's key"
done
install -m 600 "$NEW_ENV" "$ENV_FILE"
ok "SECRET_KEY and FIELD_ENCRYPTION_KEY are identical to the old server's (hash check)"

say "Restore the database"
db_sh 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "DROP DATABASE IF EXISTS \`$MYSQL_DATABASE\`; CREATE DATABASE \`$MYSQL_DATABASE\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" 2>/dev/null' \
  || die "could not recreate the database"
gunzip -c "$WORK/db.sql.gz" | db_sh 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 "$MYSQL_DATABASE" 2>/dev/null' \
  || die "the dump did not load"
table_counts > "$WORK/db-counts.new.tsv"
COUNT_RC=0
python3 - "$WORK" <<'PY' || COUNT_RC=$?
import json, os, sys
work = sys.argv[1]
want = json.load(open(os.path.join(work, "manifest.json")))["database"]["tables"]
got = {k: int(v) for k, v in (l.rstrip("\n").split("\t") for l in open(os.path.join(work, "db-counts.new.tsv")) if l.strip())}
diff = [(t, want.get(t), got.get(t)) for t in sorted(set(want) | set(got)) if want.get(t) != got.get(t)]
for t, w, g in diff:
    print(f"    {t}: manifest {w} — restored {g}")
print(f"    {len(want)} tables, {sum(want.values())} rows in the manifest; {len(got)} tables, {sum(got.values())} rows restored")
sys.exit(1 if diff else 0)
PY
if [ "$COUNT_RC" = 0 ]; then ok "row counts match the manifest in every table"
elif [ "$A_FINAL" = True ]; then die "row counts differ from the manifest of a FINAL export — do not go live with this copy"
else warn "row counts differ in the tables above: this was a test copy of a LIVE site (rows written between the dump and the count). The FINAL export must match exactly."; fi

say "Restore the media volume"
MEDIA_VOL="$(volume_name media_data)"
docker run --rm -i --network none -v "$MEDIA_VOL:/m" --entrypoint sh "$BACKEND_IMAGE" \
  -c 'find /m -mindepth 1 -delete && tar -xf - -C /m' < "$WORK/media.tar"
if [ -s "$WORK/media.sha256" ]; then
  docker run --rm -i --network none -v "$MEDIA_VOL:/m:ro" --entrypoint sh "$BACKEND_IMAGE" \
    -c 'cd /m && sha256sum -c --quiet -' < "$WORK/media.sha256" || die "media files differ from the manifest"
fi
GOT_FILES=$(docker run --rm --network none -v "$MEDIA_VOL:/m:ro" --entrypoint sh "$BACKEND_IMAGE" -c 'find /m -type f | wc -l')
[ "$GOT_FILES" = "$(mf 'm["media"]["files"]')" ] || die "media: $GOT_FILES files restored, manifest says $(mf 'm["media"]["files"]')"
ok "$GOT_FILES files, every checksum matches"

say "Mail config + TLS"
rm -rf "$ROOT/mail/config"; tar -C "$ROOT" -xf "$WORK/mail-config.tar"
ok "mail/config restored ($(mf 'm["dkim_files"]') DKIM file(s) in the archive)"
if [ -f "$WORK/tls.tar" ] && [ "$TLS" = 1 ]; then
  for d in nginx/letsencrypt nginx/manual-certs; do
    [ -n "$(ls -A "$ROOT/$d" 2>/dev/null)" ] && tar -C "$ROOT" -rf "$SAFE/tls.tar" "$d" 2>/dev/null || true
  done
  # replace only the directories the archive carries
  for d in $(tar -tf "$WORK/tls.tar" | cut -d/ -f1-2 | sort -u); do rm -rf "${ROOT:?}/$d"; done
  tar -C "$ROOT" -xf "$WORK/tls.tar"
  ok "TLS certificates restored — HTTPS works before DNS is switched (hosts-file test)"
else
  warn "no TLS in the archive (or --no-tls): issue a certificate after DNS points here (scripts/init-letsencrypt.sh --prod)"
fi

say "Migrations + seed + static (one-off container)"
$COMPOSE run --rm --no-deps -T web sh -c \
  'python manage.py migrate --noinput && python manage.py seed && python manage.py collectstatic --noinput >/dev/null' 2>&1 | tail -n 4 | sed 's/^/    /'

say "Start web (bots + celery stay on hold)"
$COMPOSE up -d --no-deps --force-recreate web daphne $WORKERS >/dev/null 2>&1 || die "could not start the backend services"
$COMPOSE up -d --no-deps --force-recreate nginx >/dev/null 2>&1 || warn "nginx did not restart — check: $COMPOSE logs nginx"
$COMPOSE up -d --no-deps --force-recreate mailserver >/dev/null 2>&1 || warn "mailserver did not restart (fine if mail goes through the admin-panel relay)"
WEB_OK=0
for i in $(seq 1 90); do      # the compose healthcheck calls /api/v1/health/ inside the container
  cid=$($COMPOSE ps -q web 2>/dev/null | head -1)
  [ "$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null)" = healthy ] && { WEB_OK=1; break; }
  sleep 2
done
[ "$WEB_OK" = 1 ] || die "web did not become healthy — $COMPOSE logs --tail 50 web"
ok "web is healthy (/api/v1/health/)"
sleep 2; workers_held || die "bots/celery are NOT on hold — stop them now: $COMPOSE stop $WORKERS"
ok "bots + celery are on hold"

say "Encrypted fields (panel password, bot tokens, SMTP password) decrypt with the restored key"
$COMPOSE exec -T web python manage.py shell -c '
from django.apps import apps
from apps.common.fields import EncryptedCharField, EncryptedTextField
ok = bad = 0
for m in apps.get_models():
    for f in (f.name for f in m._meta.fields if isinstance(f, (EncryptedCharField, EncryptedTextField))):
        for pk in m.objects.values_list("pk", flat=True):
            try:
                m.objects.values_list(f, flat=True).get(pk=pk); ok += 1
            except Exception:
                bad += 1; print("    cannot decrypt", m.__name__, pk, f)
print(f"    {ok} values readable, {bad} unreadable")
raise SystemExit(1 if bad else 0)
' 2>&1 | grep -v "objects imported" || die "some encrypted values cannot be read — FIELD_ENCRYPTION_KEY is wrong"

rm -f "$FLAG"
echo
say "Import finished — this server serves the copied data; bots + celery are ON HOLD"
status
cat <<EOF

    Next:
      1. test this server BEFORE switching DNS (hosts-file override):
           ./scripts/migrate-check.sh $(env_get SERVER_IP | grep . || echo NEW_SERVER_IP) $A_DOMAIN
         and the manual checklist in docs/migration.md
      2. $([ "$A_FINAL" = True ] && echo "this was the FINAL export: switch DNS to this server" || echo "this was a TEST copy: later run the FINAL export on the old server and import it here again")
      3. only then:  ./scripts/migrate-import.sh --start-workers
    What was here before the import is kept in ${SAFE#$ROOT/}
EOF
