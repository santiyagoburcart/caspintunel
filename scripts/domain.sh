#!/usr/bin/env bash
# Site domain (docs/domain.md). Runs on the HOST — the web container never gets
# docker access; Settings → Domain & Cloudflare only writes a request file.
#
#   ./scripts/domain.sh show            current domain, transition, pending request, last result, certificates
#   ./scripts/domain.sh rollback        back to the previous domain (recovery: works without the panel)
#   ./scripts/domain.sh retire          stop serving the old domain now (normally automatic after the transition)
#   ./scripts/domain.sh apply-request   run backups/.domain-request.json (cron, every minute)
#
# A switch: certificate check → nginx config (new domain + 301 from the old one)
# → nginx -t → reload → .env (DOMAIN, ALLOWED_HOSTS, CSRF, PUBLIC_BASE_URL, …)
# → app containers recreated (web/daphne rolling) → verified through nginx over
# TLS. Any failure restores .env + nginx config and the previous containers.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
COMPOSE="${DOMAIN_COMPOSE:-docker compose -f docker-compose.yml -f docker-compose.prod.yml}"
ENVF="$ROOT/.env"
DDIR="$ROOT/nginx/domain"; ACTIVE="$DDIR/active.conf"           # mounted in nginx at /etc/nginx/domain
SDIR="$ROOT/.domain-state"; STATE="$SDIR/state.json"            # git-ignored, root only (.env backups live here)
REQ="$ROOT/backups/.domain-request.json"; STATUS="$ROOT/backups/.domain-status.json"
PUB="$ROOT/backups/.domain-state.json"                          # what the panel shows (no secrets)
LE="$ROOT/nginx/letsencrypt"
OTHERS="${DOMAIN_APP_OTHERS:-celery_worker celery_beat bot_sales bot_backup}"
INCLUDE='include /etc/nginx/domain/active.conf;'

say() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
jget() { python3 -c "import json,sys;v=json.load(open(sys.argv[1])).get(sys.argv[2]);print('' if v is None else (int(v) if isinstance(v,bool) else v))" "$1" "$2" 2>/dev/null || true; }
envget() { python3 - "$ENVF" "$1" <<'PY'
import sys
for line in open(sys.argv[1]):
    k, _, v = line.rstrip("\n").partition("=")
    if k.strip() == sys.argv[2]:
        print(v.strip().strip('"').strip("'")); break
PY
}

ID=""; ACTION=""; BY=""
write_status() {  # ok message [expires]
  mkdir -p "$(dirname "$STATUS")"
  python3 - "$STATUS" "$1" "$2" "${3:-}" "$ID" "$ACTION" "$BY" "$(envget DOMAIN)" <<'PY'
import json, sys, time
path, ok, msg, exp, rid, action, by, dom = sys.argv[1:9]
json.dump({"ok": ok == "1", "message": msg, "expires": exp or None, "id": int(rid) if rid.isdigit() else None,
           "action": action, "requested_by": by, "domain": dom,
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, open(path, "w"))
PY
}
write_state() {  # domain www old_domain old_until previous previous_www change_id
  mkdir -p "$SDIR"; chmod 700 "$SDIR"
  python3 - "$STATE" "$PUB" "$@" <<'PY'
import json, sys, time
st, pub, dom, www, old, until, prev, pwww, cid = sys.argv[1:10]
d = {"domain": dom, "www": www == "1", "old_domain": old or None, "old_until": int(until) if until.isdigit() else None,
     "previous_domain": prev or None, "previous_www": pwww == "1", "change_id": int(cid) if cid.isdigit() else None,
     "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
for p in (st, pub):
    json.dump(d, open(p, "w"))
PY
}
sget() { [ -f "$STATE" ] && jget "$STATE" "$1" || true; }

# ---------------------------------------------------------------- certificates
cert_dir() { echo "$LE/live/$1"; }
cert_check() {  # domain www → "" when fine, else the reason
  local d="$1" w="${2:-0}" c; c="$(cert_dir "$d")/fullchain.pem"
  [ -s "$c" ] && [ -s "$(cert_dir "$d")/privkey.pem" ] || { echo "no certificate for $d (nginx/letsencrypt/live/$d)"; return; }
  openssl x509 -in "$c" -noout -checkend 3600 >/dev/null 2>&1 || { echo "the certificate for $d has expired"; return; }
  local san; san="$(openssl x509 -in "$c" -noout -ext subjectAltName 2>/dev/null | tr ',' '\n' | sed 's/.*DNS://' | tr -d ' ')"
  printf '%s\n' "$san" | grep -qx "$d" || { echo "the certificate does not cover $d"; return; }
  if [ "$w" = 1 ]; then printf '%s\n' "$san" | grep -qx "www.$d" || { echo "the certificate does not cover www.$d"; return; }; fi
}
cert_expiry() { openssl x509 -in "$(cert_dir "$1")/fullchain.pem" -noout -enddate 2>/dev/null | cut -d= -f2; }
manual_cert() { [ -s "$ROOT/nginx/manual-certs/fullchain.pem" ]; }

issue() {  # domain www
  local d="$1" w="$2" doms out ip why
  manual_cert && { write_status 0 "a manually uploaded certificate is active (nginx/manual-certs) — remove it first"; return 1; }
  doms=(-d "$d"); [ "$w" = 1 ] && doms+=(-d "www.$d")
  ip="$(envget SERVER_IP)"
  if [ -n "$ip" ] && dig +short A "mail.$d" @1.1.1.1 2>/dev/null | grep -qx "$ip"; then doms+=(-d "mail.$d"); fi
  say "certificate: ${doms[*]}"
  if [ -n "${DOMAIN_CERTBOT:-}" ]; then
    out="$($DOMAIN_CERTBOT "$d" "${doms[@]}" 2>&1)" || { why="$(printf '%s' "$out" | tail -3 | tr '\n' ' ')"; write_status 0 "certificate not issued: $why"; return 1; }
  else
    local email; email="$(envget LETSENCRYPT_EMAIL)"; email="${email:-admin@$d}"
    out="$($COMPOSE run --rm --no-deps -T --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
           --cert-name "$d" --expand "${doms[@]}" --email "$email" --agree-tos --no-eff-email --non-interactive \
           --keep-until-expiring 2>&1)" || {
      why="$(printf '%s\n' "$out" | grep -E 'Detail:|Error|error:' | tail -2 | tr '\n' ' ')"
      write_status 0 "certificate not issued: ${why:-$(printf '%s' "$out" | tail -2 | tr '\n' ' ')}"; return 1; }
  fi
  why="$(cert_check "$d" "$w")"
  [ -z "$why" ] || { write_status 0 "certificate check failed: $why"; return 1; }
  write_status 1 "certificate issued for ${doms[*]//-d /}" "$(cert_expiry "$d")"
  say "certificate ok (expires $(cert_expiry "$d"))"
}

# ---------------------------------------------------------------- nginx
render() {  # new new_www old  → nginx config on stdout
  local n="$1" nw="$2" o="${3:-}" names
  names="$n"; [ "$nw" = 1 ] && names="$n www.$n"
  cat <<EOF
# generated by scripts/domain.sh — do not edit (docs/domain.md)
server {
    listen 443 ssl;
    http2 on;
    server_name $names;
    ssl_certificate     /etc/letsencrypt/live/$n/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$n/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache  shared:SSL:10m;
    client_max_body_size 15m;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
    }
}
EOF
  [ -n "$o" ] || return 0
  local redirect="location / { if (\$request_method !~ ^(GET|HEAD)\$) { return 308 https://$n\$request_uri; } return 301 https://$n\$request_uri; }"
  cat <<EOF

# old domain $o → https://$n (301; 308 for POST etc. so the method + body survive) until it is retired
server {
    listen 80;
    server_name $o www.$o;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    $redirect
}
EOF
  if [ -s "$(cert_dir "$o")/fullchain.pem" ]; then cat <<EOF
server {
    listen 443 ssl;
    http2 on;
    server_name $o www.$o;
    ssl_certificate     /etc/letsencrypt/live/$o/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$o/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    $redirect
}
EOF
  fi
}
nginx_apply() {  # point 10-ssl.conf at our file, test, reload
  $COMPOSE exec -T nginx sh -c "printf '%s\n' '$INCLUDE' > /etc/nginx/conf.d/10-ssl.conf" >/dev/null 2>&1 || return 1
  $COMPOSE exec -T nginx nginx -t >/dev/null 2>&1 || { echo "nginx -t rejected the config"; return 1; }
  $COMPOSE exec -T nginx nginx -s reload >/dev/null 2>&1
}

# ---------------------------------------------------------------- .env
env_switch() {  # new new_www drop… — DOMAIN/hosts/origins/URLs follow the new domain; dropped domains leave the lists
  local n="$1" nw="$2"; shift 2
  python3 - "$ENVF" "$n" "$nw" "${ZONE:-}" "$*" <<'PY'
import os, sys
path, new, new_www, zone, drop = sys.argv[1], sys.argv[2], sys.argv[3] == "1", sys.argv[4], sys.argv[5].split()
lines = open(path).read().splitlines()
env = {}
for l in lines:
    k, sep, v = l.partition("=")
    if sep and not k.lstrip().startswith("#"):
        env[k.strip()] = v.strip().strip('"').strip("'")
old = env.get("DOMAIN", "")
gone = set()
for d in drop:
    gone |= {d, "www." + d}
want = [new] + (["www." + new] if new_www else [])
def merge(cur, add, fmt):
    items = [x.strip() for x in cur.split(",") if x.strip()]
    items = [x for x in items if x.replace("https://", "").replace("http://", "") not in gone]
    for a in add:
        if fmt(a) not in items:
            items.append(fmt(a))
    return ",".join(items)
upd = {"DOMAIN": new, "PUBLIC_BASE_URL": f"https://{new}",
       "ALLOWED_HOSTS": merge(env.get("ALLOWED_HOSTS", ""), want, lambda h: h),
       "CSRF_TRUSTED_ORIGINS": merge(env.get("CSRF_TRUSTED_ORIGINS", ""), want, lambda h: f"https://{h}")}
cors = env.get("CORS_ALLOWED_ORIGINS", "")
if cors:
    upd["CORS_ALLOWED_ORIGINS"] = merge(cors, want if any(old in c for c in cors.split(",")) else [], lambda h: f"https://{h}")
mini = env.get("MINIAPP_URL", "")
if mini and old and old in mini:
    upd["MINIAPP_URL"] = mini.replace(old, new)
if zone:
    upd["CLOUDFLARE_ZONE"] = zone
if not env.get("MAIL_DOMAIN") and old:
    upd["MAIL_DOMAIN"] = old          # the mail server keeps its identity; moving mail is a manual step
out, seen = [], set()
for l in lines:
    k, sep, _ = l.partition("=")
    if sep and k.strip() in upd and not k.lstrip().startswith("#"):
        out.append(f"{k.strip()}={upd[k.strip()]}"); seen.add(k.strip())
    else:
        out.append(l)
out += [f"{k}={v}" for k, v in upd.items() if k not in seen]
mode = os.stat(path).st_mode & 0o777
tmp = path + ".domain-tmp"
with open(tmp, "w") as f:
    f.write("\n".join(out) + "\n")
os.chmod(tmp, mode)
os.replace(tmp, path)
PY
}

# ---------------------------------------------------------------- containers
rollout() {  # same as update.sh: new container next to the old one, healthy → retire the old one
  local svc=$1 old new i
  old=$($COMPOSE ps -q "$svc" | head -1)
  if [ -z "$old" ]; then return 0; fi
  $COMPOSE up -d --no-deps --no-recreate --scale "$svc=2" "$svc" >/dev/null 2>&1 || return 1
  new=$($COMPOSE ps -q "$svc" | grep -v "$old" | head -1)
  [ -n "$new" ] || { echo "$svc: no new container"; return 1; }
  for i in $(seq 1 60); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$new" 2>/dev/null)" = "healthy" ] && break
    sleep 2
  done
  if [ "$(docker inspect -f '{{.State.Health.Status}}' "$new" 2>/dev/null)" != "healthy" ]; then
    docker rm -f "$new" >/dev/null 2>&1 || true
    echo "$svc: the new container never became healthy"; return 1
  fi
  sleep 3
  docker stop -t 35 "$old" >/dev/null; docker rm "$old" >/dev/null
}
restart_apps() {
  local svc
  for svc in web daphne; do rollout "$svc" || return 1; done
  for svc in $OTHERS; do
    [ -n "$($COMPOSE ps -q "$svc" 2>/dev/null)" ] && { $COMPOSE up -d --no-deps "$svc" >/dev/null 2>&1 || { echo "$svc did not start"; return 1; }; }
  done
  return 0
}

# ---------------------------------------------------------------- verify (through nginx, over TLS)
probe() {  # host url → "code redirect"
  local ip; ip="$($COMPOSE exec -T web getent hosts nginx 2>/dev/null | awk 'NR==1{print $1}')"
  local port=443; case "$2" in http://*) port=80 ;; esac
  $COMPOSE exec -T web curl -sk -o /dev/null --max-time 15 -w '%{http_code} %{redirect_url}' \
    --resolve "$1:$port:$ip" "$2" 2>/dev/null || true
}
verify() {  # new old
  local n="$1" o="${2:-}" r i
  for i in 1 2 3 4 5; do r="$(probe "$n" "https://$n/api/v1/health/")"; [ "${r%% *}" = 200 ] && break; sleep 3; done
  [ "${r%% *}" = 200 ] || { echo "https://$n/api/v1/health/ answered ${r:-nothing}"; return 1; }
  [ -n "$o" ] || return 0
  r="$(probe "$o" "https://$o/store?x=1")"
  if [ -s "$(cert_dir "$o")/fullchain.pem" ] && [ "$r" != "301 https://$n/store?x=1" ]; then echo "https://$o does not redirect to $n (got: $r)"; return 1; fi
  r="$(probe "$o" "http://$o/store")"
  [ "$r" = "301 https://$n/store" ] || { echo "http://$o does not redirect to $n (got: $r)"; return 1; }
}

# ---------------------------------------------------------------- one switch, all or nothing
switch() {  # new new_www keep_old(redirecting, or "") old_until drop… ; state after: previous = the domain we leave
  local n="$1" nw="$2" keep="$3" until="$4"; shift 4
  local cur cur_www why
  cur="$(envget DOMAIN)"; cur_www="$(sget www)"; cur_www="${cur_www:-1}"
  manual_cert && { write_status 0 "a manually uploaded certificate is active (nginx/manual-certs) — remove it first"; return 1; }
  why="$(cert_check "$n" "$nw")"
  [ -z "$why" ] || { write_status 0 "not switched: $why"; return 1; }
  mkdir -p "$DDIR" "$SDIR"; chmod 700 "$SDIR"
  cp -p "$ENVF" "$SDIR/env.before"; chmod 600 "$SDIR/env.before"
  if [ -s "$ACTIVE" ]; then cp -p "$ACTIVE" "$SDIR/active.before"
  elif [ -n "$cur" ] && [ -z "$(cert_check "$cur" 0)" ]; then render "$cur" "$cur_www" "" > "$SDIR/active.before"   # adopt today's setup
  else rm -f "$SDIR/active.before"; fi
  [ -f "$STATE" ] && cp -p "$STATE" "$SDIR/state.before" || rm -f "$SDIR/state.before"
  render "$n" "$nw" "$keep" > "$ACTIVE.tmp" && mv "$ACTIVE.tmp" "$ACTIVE"; chmod 644 "$ACTIVE"
  say "nginx: $n${keep:+ (+ $keep → 301)}"
  if why="$(nginx_apply)"; then
    say ".env: DOMAIN=$n"
    why=".env could not be updated"
    if env_switch "$n" "$nw" "$@" && say "app containers (web/daphne rolling, $OTHERS)" && why="$(restart_apps)"; then
      say "verify"
      if why="$(verify "$n" "$keep")"; then
        local prev="$cur" pwww="$cur_www"
        [ "$cur" = "$n" ] && { prev="$(sget previous_domain)"; pwww="$(sget previous_www)"; }
        write_state "$n" "$nw" "$keep" "$until" "$prev" "$pwww" "$ID"
        rm -f "$SDIR/active.before"
        return 0
      fi
    fi
  fi
  say "FAILED: $why — restoring $cur"
  cp -p "$SDIR/env.before" "$ENVF"
  if [ -s "$SDIR/active.before" ]; then cp -p "$SDIR/active.before" "$ACTIVE"; nginx_apply >/dev/null || true
  else rm -f "$ACTIVE"; $COMPOSE restart nginx >/dev/null 2>&1 || true; fi
  [ -f "$SDIR/state.before" ] && cp -p "$SDIR/state.before" "$STATE"
  restart_apps >/dev/null || true
  write_status 0 "rolled back to $cur: $why"
  return 1
}

do_apply() {  # new www old days
  local n="$1" w="$2" o="$3" days="${4:-14}"
  if [ "$days" -gt 0 ] 2>/dev/null; then
    switch "$n" "$w" "$o" "$(( $(date +%s) + days * 86400 ))" || return 1
    write_status 1 "live on https://$n — $o redirects to it for $days days"
  else
    switch "$n" "$w" "" "" "$o" || return 1
    write_status 1 "live on https://$n — $o is no longer served"
  fi
  say "domain: https://$n/"
}
do_retire() {
  local n o; n="$(envget DOMAIN)"; o="$(sget old_domain)"
  [ -n "$o" ] || { write_status 1 "no old domain to remove"; say "nothing to retire"; return 0; }
  switch "$n" "$(sget www)" "" "" "$o" || return 1
  write_status 1 "$o removed — only https://$n is served"
  say "$o retired"
}
do_rollback() {
  local p pw cur; p="$(sget previous_domain)"; pw="$(sget previous_www)"; cur="$(envget DOMAIN)"
  [ -n "$p" ] || { write_status 0 "no previous domain recorded"; die "no previous domain recorded"; }
  [ -n "$ID" ] || ID="$(sget change_id)"
  switch "$p" "${pw:-1}" "" "" "$cur" || return 1
  write_status 1 "back on https://$p — $cur is no longer served"
  say "rolled back to https://$p/"
}

mkdir -p "$ROOT/backups"
exec 9>"$ROOT/backups/.domain.lock" 2>/dev/null || exec 9>/tmp/caspintunel-domain.lock
flock -n 9 || { echo "another domain change is running"; exit 0; }

case "${1:-show}" in
  show)
    echo "domain      : $(envget DOMAIN)"
    if [ -f "$STATE" ]; then
      echo "old domain  : $(sget old_domain)  (redirects until $(u="$(sget old_until)"; [ -n "$u" ] && date -d "@$u" '+%F %R' || echo -))"
      echo "previous    : $(sget previous_domain)   (./scripts/domain.sh rollback)"
    fi
    for d in "$(envget DOMAIN)" "$(sget old_domain)" "$(sget previous_domain)"; do
      [ -n "$d" ] && [ -s "$(cert_dir "$d")/fullchain.pem" ] && echo "certificate : $d expires $(cert_expiry "$d")"
    done
    [ -f "$REQ" ] && echo "pending     : $(cat "$REQ")"
    [ -f "$STATUS" ] && echo "last result : $(cat "$STATUS")"
    true ;;
  rollback) ACTION=rollback; BY=cli; do_rollback ;;
  retire) ACTION=retire; BY=cli; ID="$(sget change_id)"; do_retire ;;
  apply-request)
    [ -f "$REQ" ] || exit 0
    ACTION="$(jget "$REQ" action)"; ID="$(jget "$REQ" id)"; BY="$(jget "$REQ" requested_by)"
    D="$(jget "$REQ" domain)"; W="$(jget "$REQ" www)"; O="$(jget "$REQ" old_domain)"; DAYS="$(jget "$REQ" transition_days)"
    ZONE="$(jget "$REQ" zone)"
    rm -f "$REQ"                                   # one attempt per request, never a loop
    if ! printf '%s' "$D" | grep -qE '^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$'; then
      write_status 0 "rejected: invalid domain"; die "invalid domain"
    fi
    say "$(date -u +%FT%TZ) $ACTION $D (by ${BY:-?})"
    case "$ACTION" in
      cert) issue "$D" "${W:-1}" ;;
      apply) [ "$(envget DOMAIN)" = "$O" ] || { write_status 0 "rejected: the site is on $(envget DOMAIN), not $O"; die "domain moved meanwhile"; }
             do_apply "$D" "${W:-1}" "$O" "${DAYS:-14}" ;;
      retire) do_retire ;;
      rollback) do_rollback ;;
      *) write_status 0 "rejected: unknown action"; die "unknown action $ACTION" ;;
    esac ;;
  *) sed -n '2,9p' "$0"; exit 2 ;;
esac
