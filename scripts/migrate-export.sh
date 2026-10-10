#!/usr/bin/env bash
# Server migration, step 1 — run on the OLD server.  Runbook: docs/migration.md
#
#   ./scripts/migrate-export.sh                 test copy: the site keeps running
#   ./scripts/migrate-export.sh --final         maintenance mode + bots/celery on hold FIRST,
#                                               then the export (no order can arrive meanwhile)
#   ./scripts/migrate-export.sh --resume        undo --final: reopen the site, start bots/celery
#
#   --passphrase-file FILE   read the archive passphrase from FILE (else: prompt / MIGRATE_PASSPHRASE)
#   --out DIR                where the archive goes (default backups/migration)
#   --no-tls                 leave the TLS certificates out
#   --yes                    no confirmation question (--final / --resume)
#
# One AES-256 encrypted archive: consistent DB dump, the whole media volume,
# .env, mail config (+ DKIM keys), TLS certificates and manifest.json (version,
# commit, exact row count per table, file counts, SHA-256 of every part).
# A plain export only READS: nothing on the server is changed.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/migrate-lib.sh"

MODE=export; FINAL=0; YES=0; TLS=1; PASSFILE=""; OUT="$MIG_DIR"
while [ $# -gt 0 ]; do
  case "$1" in
    --final) FINAL=1 ;;
    --resume) MODE=resume ;;
    --yes) YES=1 ;;
    --no-tls) TLS=0 ;;
    --passphrase-file) PASSFILE="${2:?}"; shift ;;
    --out) OUT="${2:?}"; shift ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac; shift
done

need docker openssl tar gzip sha256sum python3
[ -f "$ENV_FILE" ] || die "no .env here — is this the installed server?"

if [ "$MODE" = resume ]; then
  say "Resume normal operation on THIS server"
  echo "    Only do this if the new server's bots/celery are NOT running (the same bot must never poll twice)."
  if [ "$YES" != 1 ]; then read -r -p "    type RESUME to continue: " a; [ "$a" = RESUME ] || die "aborted"; fi
  release_workers
  maintenance_off
  exit 0
fi

db_ready || die "the database container is not running/healthy"
VERSION="$(cat VERSION)"
COMMIT="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
NAME="caspintunel-migration-$VERSION-$STAMP$([ "$FINAL" = 1 ] && echo -final || true)"
load_passphrase "$PASSFILE" 1

mkdir -p "$OUT"; chmod 700 "$OUT"
WORK="$(mktemp -d "$OUT/.export-XXXXXX")"; chmod 700 "$WORK"
trap 'rm -rf "$WORK"' EXIT

if [ "$FINAL" = 1 ]; then
  say "FINAL export: the site goes into maintenance mode and bots/celery are put on hold"
  echo "    Visitors see a 'moving to a new server' page until you run --resume here"
  echo "    or switch DNS to the new server."
  if [ "$YES" != 1 ]; then read -r -p "    type FINAL to continue: " a; [ "$a" = FINAL ] || die "aborted"; fi
  maintenance_on
  hold_workers
  sleep 8        # in-flight web requests and the last celery task finish
fi

say "Database dump (single transaction = one consistent snapshot)"
db_sh 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers --no-tablespaces --default-character-set=utf8mb4 "$MYSQL_DATABASE"' 2>/dev/null \
  | gzip > "$WORK/db.sql.gz"
gunzip -c "$WORK/db.sql.gz" | tail -n 3 | grep -q "Dump completed" || die "the dump is incomplete"
table_counts > "$WORK/db-counts.tsv"
[ -s "$WORK/db-counts.tsv" ] || die "could not count rows"
ok "$(wc -l < "$WORK/db-counts.tsv") tables, $(awk -F'\t' '{s+=$2} END {print s}' "$WORK/db-counts.tsv") rows, $(human "$(stat -c %s "$WORK/db.sql.gz")")"

say "Media volume"
MEDIA_VOL="$(volume_name media_data)"
docker run --rm --network none -v "$MEDIA_VOL:/m:ro" --entrypoint sh "$BACKEND_IMAGE" -c 'cd /m && tar -cf - .' > "$WORK/media.tar"
docker run --rm --network none -v "$MEDIA_VOL:/m:ro" --entrypoint sh "$BACKEND_IMAGE" \
  -c 'cd /m && find . -type f -print0 | sort -z | xargs -0 -r sha256sum' > "$WORK/media.sha256"
ok "$(wc -l < "$WORK/media.sha256") files, $(human "$(stat -c %s "$WORK/media.tar")")"

say ".env, mail config, TLS"
grep -v '^MIGRATION_HOLD=' "$ENV_FILE" > "$WORK/env"; chmod 600 "$WORK/env"
mkdir -p "$ROOT/mail/config"
tar -C "$ROOT" -cf "$WORK/mail-config.tar" mail/config
DKIM=$(find "$ROOT/mail/config" -type f \( -name '*.private' -o -path '*opendkim*' \) 2>/dev/null | wc -l)
if [ "$DKIM" -gt 0 ]; then ok "mail config with $DKIM DKIM file(s)"
else warn "no DKIM key files under mail/config (this server sends through a relay) — nothing to carry over"; fi
TLS_PARTS=""
if [ "$TLS" = 1 ]; then
  for d in nginx/letsencrypt nginx/manual-certs; do
    [ -n "$(ls -A "$ROOT/$d" 2>/dev/null)" ] && TLS_PARTS="$TLS_PARTS $d"
  done
  if [ -n "$TLS_PARTS" ]; then tar -C "$ROOT" -cf "$WORK/tls.tar" $TLS_PARTS; ok "TLS:$TLS_PARTS"; fi
fi

say "Manifest"
FINAL="$FINAL" VERSION="$VERSION" COMMIT="$COMMIT" FORMAT="$FORMAT" DKIM="$DKIM" \
SECRET_SHA="$(key_hash SECRET_KEY)" FIELD_SHA="$(key_hash FIELD_ENCRYPTION_KEY)" \
DOMAIN="$(env_get DOMAIN)" DB_NAME="$(env_get DB_NAME)" python3 - "$WORK" <<'PY'
import hashlib, json, os, socket, sys, time
work = sys.argv[1]
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
counts = dict(line.rstrip("\n").split("\t") for line in open(os.path.join(work, "db-counts.tsv")) if line.strip())
media = [l for l in open(os.path.join(work, "media.sha256")) if l.strip()]
files = {n: {"sha256": sha(os.path.join(work, n)), "size": os.path.getsize(os.path.join(work, n))}
         for n in sorted(os.listdir(work)) if n != "manifest.json"}
env = os.environ
manifest = {
    "format": int(env["FORMAT"]), "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "final": env["FINAL"] == "1", "version": env["VERSION"], "commit": env["COMMIT"],
    "source_host": socket.gethostname(), "domain": env["DOMAIN"],
    "database": {"name": env["DB_NAME"], "tables": {k: int(v) for k, v in counts.items()},
                 "total_rows": sum(int(v) for v in counts.values())},
    "media": {"files": len(media)}, "dkim_files": int(env["DKIM"]),
    # hashes only — lets the import prove the SAME keys arrived without exposing them
    "keys": {"SECRET_KEY": env["SECRET_SHA"], "FIELD_ENCRYPTION_KEY": env["FIELD_SHA"]},
    "files": files,
}
json.dump(manifest, open(os.path.join(work, "manifest.json"), "w"), indent=1, sort_keys=True)
PY
ok "manifest.json"

say "Encrypt (AES-256, PBKDF2)"
ARCHIVE="$OUT/$NAME.tar.enc"
tar -C "$WORK" -cf - . | encrypt > "$ARCHIVE"
chmod 600 "$ARCHIVE"
decrypt < "$ARCHIVE" | tar -tf - >/dev/null || die "the archive does not decrypt cleanly"
( cd "$OUT" && sha256sum "$NAME.tar.enc" > "$NAME.tar.enc.sha256" )
ok "verified: decrypts and lists"

IP="$(env_get SERVER_IP)"
echo
say "Done"
echo "    archive : $ARCHIVE"
echo "    size    : $(human "$(stat -c %s "$ARCHIVE")")"
echo "    sha256  : $(cut -d' ' -f1 "$ARCHIVE.sha256")"
echo "    version : $VERSION ($COMMIT)"
echo
echo "    Copy BOTH files to the new server (run on the NEW server):"
echo "      rsync -avP -e ssh root@${IP:-OLD_SERVER_IP}:$ARCHIVE root@${IP:-OLD_SERVER_IP}:$ARCHIVE.sha256 /root/caspintunel/backups/migration/"
echo "    or from here:"
echo "      scp $ARCHIVE $ARCHIVE.sha256 root@NEW_SERVER_IP:/root/caspintunel/backups/migration/"
echo "    then on the new server:"
echo "      ./scripts/migrate-import.sh backups/migration/$NAME.tar.enc"
if [ "$FINAL" = 1 ]; then
  echo
  echo "    This server is now in MAINTENANCE with bots/celery on hold. It stays that way"
  echo "    (reboots and ./update.sh included) until:  ./scripts/migrate-export.sh --resume"
fi
