#!/usr/bin/env bash
# Site domain (docs/domain.md). Runs on the HOST — the web container never gets
# docker access; Settings → Domain & Cloudflare only writes a request file.
#
#   ./scripts/domain.sh show            current domain, transition, pending request, last result, certificates
#   ./scripts/domain.sh rollback        back to the previous domain (recovery: works without the panel)
#   ./scripts/domain.sh retire          stop serving the old domain now (normally automatic after the transition)
#   ./scripts/domain.sh access          re-render nginx for the access mode (Cloudflare ranges, PROXY listeners)
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
OTHERS="${DOMAIN_APP_OTHERS-celery_worker celery_beat bot_sales bot_backup mailserver}"
DKIM="$ROOT/backups/.domain-dkim.json"                          # public DKIM record of the new domain (for DNS)
MAIL=0                                                          # 1: the cert must cover mail.<domain> (mail moves with the domain)
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
cert_check() {  # domain www [mail] → "" when fine, else the reason
  local d="$1" w="${2:-0}" m="${3:-0}" c; c="$(cert_dir "$d")/fullchain.pem"
  [ -s "$c" ] && [ -s "$(cert_dir "$d")/privkey.pem" ] || { echo "no certificate for $d (nginx/letsencrypt/live/$d)"; return; }
  openssl x509 -in "$c" -noout -checkend 3600 >/dev/null 2>&1 || { echo "the certificate for $d has expired"; return; }
  local san; san="$(openssl x509 -in "$c" -noout -ext subjectAltName 2>/dev/null | tr ',' '\n' | sed 's/.*DNS://' | tr -d ' ')"
  printf '%s\n' "$san" | grep -qx "$d" || { echo "the certificate does not cover $d"; return; }
  if [ "$w" = 1 ]; then printf '%s\n' "$san" | grep -qx "www.$d" || { echo "the certificate does not cover www.$d"; return; }; fi
  if [ "$m" = 1 ]; then printf '%s\n' "$san" | grep -qx "mail.$d" || { echo "the certificate does not cover mail.$d"; return; }; fi
}
cert_expiry() { openssl x509 -in "$(cert_dir "$1")/fullchain.pem" -noout -enddate 2>/dev/null | cut -d= -f2; }
manual_cert() { [ -s "$ROOT/nginx/manual-certs/fullchain.pem" ]; }

issue() {  # domain www
  local d="$1" w="$2" doms out ip why
  manual_cert && { write_status 0 "a manually uploaded certificate is active (nginx/manual-certs) — remove it first"; return 1; }
  doms=(-d "$d"); [ "$w" = 1 ] && doms+=(-d "www.$d")
  ip="$(envget SERVER_IP)"
  if [ "$MAIL" = 1 ] || { [ -n "$ip" ] && dig +short A "mail.$d" @1.1.1.1 2>/dev/null | grep -qx "$ip"; }; then doms+=(-d "mail.$d"); fi
  say "certificate: ${doms[*]}"
  if [ -n "${DOMAIN_CERTBOT:-}" ]; then
    out="$($DOMAIN_CERTBOT "$d" "${doms[@]}" 2>&1)" || { why="$(printf '%s' "$out" | tail -3 | tr '\n' ' ')"; write_status 0 "certificate not issued: $why"; return 1; }
  else
    local email; email="$(envget LETSENCRYPT_EMAIL)"; email="${email:-admin@$d}"
    local how=(--webroot -w /var/www/certbot)
    if [ -s "$CFINI" ]; then   # DNS-01 with the Cloudflare token: works in every access mode
      how=(--authenticator dns-cloudflare --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini --dns-cloudflare-propagation-seconds 30)
    fi
    out="$($COMPOSE run --rm --no-deps -T --entrypoint certbot certbot certonly "${how[@]}" \
           --cert-name "$d" --expand "${doms[@]}" --email "$email" --agree-tos --no-eff-email --non-interactive \
           --keep-until-expiring 2>&1)" || {
      why="$(printf '%s\n' "$out" | grep -E 'Type:|Detail:|Error|error:' | tail -3 | tr '\n' ' ')"
      write_status 0 "certificate not issued: ${why:-$(printf '%s' "$out" | tail -2 | tr '\n' ' ')}"; return 1; }
  fi
  why="$(cert_check "$d" "$w" "$MAIL")"
  [ -z "$why" ] || { write_status 0 "certificate check failed: $why"; return 1; }
  if [ "$MAIL" = 1 ]; then
    why="$(dkim_gen "$d")" || { write_status 0 "certificate ok, but no DKIM key: $why"; return 1; }
  fi
  write_status 1 "certificate issued for ${doms[*]//-d /}$([ "$MAIL" = 1 ] && echo " · DKIM key ready (selector mail)")" "$(cert_expiry "$d")"
  say "certificate ok (expires $(cert_expiry "$d"))"
}

# ---------------------------------------------------------------- mail server (DKIM + identity)
dkim_gen() {  # domain → DKIM key made by the mail server (kept if it exists), public record → $DKIM
  local d="$1" txt k="/tmp/docker-mailserver/opendkim/keys/$1"
  [ -n "$($COMPOSE ps -q mailserver 2>/dev/null)" ] || { echo "the mail server is not running"; return 1; }
  if ! $COMPOSE exec -T mailserver test -s "$k/mail.private" 2>/dev/null; then
    $COMPOSE exec -T mailserver setup config dkim keysize 2048 domain "$d" >/dev/null 2>&1 || { echo "the mail server could not create a DKIM key"; return 1; }
  fi
  txt="$($COMPOSE exec -T mailserver cat "$k/mail.txt" 2>/dev/null)" || { echo "no DKIM record for $d"; return 1; }
  printf '%s' "$txt" | python3 -c '
import json, re, sys
txt = "".join(re.findall(r"\"([^\"]*)\"", sys.stdin.read())).strip()
if "p=" not in txt:
    sys.exit("DKIM record unreadable")
json.dump({"domain": sys.argv[2], "selector": "mail", "txt": txt}, open(sys.argv[1], "w"))' "$DKIM" "$d" || { echo "DKIM record unreadable"; return 1; }
  say "DKIM: mail._domainkey.$d"
}
verify_mail() {  # domain — the recreated mail server is healthy and answers as mail.<domain>
  case " $OTHERS " in *" mailserver "*) ;; *) return 0 ;; esac
  local cid i h; cid="$($COMPOSE ps -q mailserver 2>/dev/null | head -1)"
  [ -n "$cid" ] || return 0
  for i in $(seq 1 60); do [ "$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null)" = healthy ] && break; sleep 3; done
  [ "$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null)" = healthy ] || { echo "the mail server did not become healthy"; return 1; }
  h="$($COMPOSE exec -T mailserver postconf -h myhostname 2>/dev/null | tr -d '\r')"
  [ "$h" = "mail.$1" ] || { echo "the mail server answers as '$h', not mail.$1"; return 1; }
}

# ---------------------------------------------------------------- nginx
redirect_to() {  # domain → location that sends everything to https://<domain> (301; 308 keeps POST + body)
  echo "location / { if (\$request_method !~ ^(GET|HEAD)\$) { return 308 https://$1\$request_uri; } return 301 https://$1\$request_uri; }"
}
render() {  # new new_www old  → nginx config on stdout
  local n="$1" nw="$2" o="${3:-}"
  cat <<EOF
# generated by scripts/domain.sh — do not edit (docs/domain.md)
server {
    listen 443 ssl;
    http2 on;
    server_name $n;
    ssl_certificate     /etc/letsencrypt/live/$n/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$n/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache  shared:SSL:10m;
    client_max_body_size 15m;
    include /etc/nginx/domain/realip*.conf;        # CF-Connecting-IP, only from Cloudflare's ranges (access mode)
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Conn-Addr \$realip_remote_addr;   # the TCP peer (tunnel source check)
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
    }
}
EOF
  if [ "$nw" = 1 ]; then cat <<EOF

# www.$n → https://$n (one host = one set of browser storage; path + query kept). The certificate
# still covers www, so https://www.$n answers with a valid certificate before redirecting.
server {
    listen 443 ssl;
    http2 on;
    server_name www.$n;
    ssl_certificate     /etc/letsencrypt/live/$n/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$n/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    $(redirect_to "$n")
}
server {
    listen 80;
    server_name www.$n;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    $(redirect_to "$n")
}
EOF
  fi
  render_proxy "$n" "$nw"
  [ -n "$o" ] || return 0
  local redirect; redirect="$(redirect_to "$n")"
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
# ---------------------------------------------------------------- access mode (docs/access-mode.md)
AXP="$ROOT/backups/.access-nginx.json"; REALIP="$DDIR/realip.conf"
axget() { [ -s "$AXP" ] && python3 -c "import json,sys;print(' '.join(str(x) for x in (json.load(open(sys.argv[1])).get(sys.argv[2]) or [])))" "$AXP" "$1" 2>/dev/null || true; }
render_realip() {  # Cloudflare edges → CF-Connecting-IP (anyone else keeps their own address)
  local n
  echo "# generated by scripts/domain.sh access — Cloudflare ranges (refreshed daily by the panel)"
  for n in $(axget cf_v4) $(axget cf_v6); do echo "set_real_ip_from $n;"; done
  echo "real_ip_header CF-Connecting-IP;"
}
render_proxy() {  # domain www → PROXY-protocol listeners for tunnels that send it (off by default)
  local n="$1" nw="$2" p src srcs lst names; srcs="$(axget sources)"; p=" $(axget proxy_ports) "
  [ -n "$srcs" ] || return 0
  case "$p" in *" 80 "*|*" 443 "*) ;; *) return 0 ;; esac
  printf '\n# PROXY protocol from the tunnel sources only (access mode)\ngeo $realip_remote_addr $ax_tunnel_ok {\n    default 0;\n'
  for src in $srcs; do printf '    %s 1;\n' "$src"; done
  printf '}\n'
  for lst in 443 80; do
    case "$p" in *" $lst "*) ;; *) continue ;; esac
    for names in "$n" $([ "$nw" = 1 ] && echo "www.$n"); do
    if [ "$lst" = 443 ]; then
      printf 'server {\n    listen 8843 ssl proxy_protocol;\n    http2 on;\n    server_name %s;\n' "$names"
      printf '    ssl_certificate     /etc/letsencrypt/live/%s/fullchain.pem;\n    ssl_certificate_key /etc/letsencrypt/live/%s/privkey.pem;\n' "$n" "$n"
      printf '    ssl_protocols TLSv1.2 TLSv1.3;\n    ssl_ciphers HIGH:!aNULL:!MD5;\n'
    else
      printf 'server {\n    listen 8880 proxy_protocol;\n    server_name %s;\n' "$names"
    fi
    printf '    client_max_body_size 15m;\n'
    for src in $srcs; do printf '    set_real_ip_from %s;\n' "$src"; done
    printf '    real_ip_header proxy_protocol;\n    if ($ax_tunnel_ok = 0) { return 444; }\n'
    printf '    location /.well-known/acme-challenge/ { root /var/www/certbot; }\n'
    if [ "$names" != "$n" ]; then printf '    %s\n}\n' "$(redirect_to "$n")"; continue; fi   # www → apex
    printf '    location / {\n        proxy_pass http://127.0.0.1:80;\n        proxy_set_header Host $host;\n'
    printf '        proxy_set_header X-Real-IP $remote_addr;\n        proxy_set_header X-Forwarded-For $remote_addr;\n'
    printf '        proxy_set_header X-Forwarded-Proto %s;\n' "$([ "$lst" = 443 ] && echo https || echo http)"
    printf '        proxy_set_header X-Conn-Addr $realip_remote_addr;\n        proxy_http_version 1.1;\n'
    printf '        proxy_set_header Upgrade $http_upgrade;\n        proxy_set_header Connection $connection_upgrade;\n    }\n}\n'
    done
  done
}
do_access() {  # re-render the live vhost + realip from backups/.access-nginx.json; test; reload; verify; or restore
  local n nw o why u; n="$(envget DOMAIN)"; nw="$(sget www)"; nw="${nw:-1}"; o="$(sget old_domain)"
  u="$(sget old_until)"; if [ -n "$u" ] && [ "$u" -lt "$(date +%s)" ] 2>/dev/null; then o=""; fi
  why="$(cert_check "$n" "$nw")"
  [ -z "$why" ] || { write_status 0 "access: not applied — $why"; return 1; }
  mkdir -p "$DDIR" "$SDIR"
  if [ -s "$ACTIVE" ]; then cp -p "$ACTIVE" "$SDIR/active.access"; else rm -f "$SDIR/active.access"; fi
  if [ -s "$REALIP" ]; then cp -p "$REALIP" "$SDIR/realip.access"; else rm -f "$SDIR/realip.access"; fi
  if [ -n "$(axget cf_v4)" ]; then render_realip > "$REALIP.tmp" && mv "$REALIP.tmp" "$REALIP"; chmod 644 "$REALIP"; fi
  render "$n" "$nw" "$o" > "$ACTIVE.tmp" && mv "$ACTIVE.tmp" "$ACTIVE"; chmod 644 "$ACTIVE"
  if why="$(nginx_apply)" && why="$(verify "$n" "" "$nw")"; then
    local pp; pp="$(axget proxy_ports)"
    write_status 1 "access: nginx updated — Cloudflare ranges $(axget cf_v4 | wc -w)+$(axget cf_v6 | wc -w), tunnel sources $(axget sources | wc -w), PROXY protocol: ${pp:-off}"
    say "access applied"; return 0
  fi
  say "FAILED: $why — restoring"
  if [ -s "$SDIR/active.access" ]; then cp -p "$SDIR/active.access" "$ACTIVE"; else rm -f "$ACTIVE"; fi
  if [ -s "$SDIR/realip.access" ]; then cp -p "$SDIR/realip.access" "$REALIP"; else rm -f "$REALIP"; fi
  nginx_apply >/dev/null || true
  write_status 0 "access: nginx not changed — $why"; return 1
}
CFINI="$LE/cloudflare.ini"                                       # certbot dns-cloudflare credentials (root only)
do_dns01() {  # renewal of the live certificate via DNS-01 with the panel's Cloudflare token
  local n tok out why; n="$(envget DOMAIN)"
  tok="$($COMPOSE exec -T web python manage.py cloudflare_token 2>/dev/null | tr -d '\r\n')"
  [ -n "$tok" ] || { write_status 0 "dns01: no Cloudflare token saved in the panel or .env"; return 1; }
  ( umask 077; printf 'dns_cloudflare_api_token = %s\n' "$tok" > "$CFINI.tmp" ) && mv "$CFINI.tmp" "$CFINI"; chmod 600 "$CFINI"
  tok=""
  [ -s "$(cert_dir "$n")/fullchain.pem" ] || { write_status 1 "dns01: credentials saved — new certificates use DNS-01"; return 0; }
  if [ -n "${DOMAIN_CERTBOT_RECONFIGURE:-}" ]; then
    out="$($DOMAIN_CERTBOT_RECONFIGURE "$n" 2>&1)" || { write_status 0 "dns01: renewal not switched: $(printf '%s' "$out" | tail -2 | tr '\n' ' ')"; return 1; }
  else
    out="$($COMPOSE run --rm --no-deps -T --entrypoint certbot certbot reconfigure --cert-name "$n" \
           --authenticator dns-cloudflare --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
           --dns-cloudflare-propagation-seconds 30 --non-interactive 2>&1)" || {
      why="$(printf '%s\n' "$out" | grep -E 'Type:|Detail:|Error|error:' | tail -3 | tr '\n' ' ')"
      write_status 0 "dns01: renewal not switched: ${why:-$(printf '%s' "$out" | tail -2 | tr '\n' ' ')}"; return 1; }
  fi
  write_status 1 "dns01: $n renews via DNS-01 (Cloudflare) — works in every access mode"
  say "dns01 ok for $n"
}

nginx_apply() {  # point 10-ssl.conf at our file, test, reload
  $COMPOSE exec -T nginx sh -c "printf '%s\n' '$INCLUDE' > /etc/nginx/conf.d/10-ssl.conf" >/dev/null 2>&1 || { echo "nginx container not reachable"; return 1; }
  local out; out="$($COMPOSE exec -T nginx nginx -t 2>&1)" || {
    echo "nginx -t rejected the config: $(printf '%s\n' "$out" | grep -m1 -E '\[emerg\]|\[error\]' | sed 's/^.*\(\[emerg\]\|\[error\]\)/\1/' || printf '%s\n' "$out" | tail -1)"; return 1; }
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
upd["MAIL_DOMAIN"] = new               # mail moves with the domain (hostname mail.<new>, its cert, DKIM)
frm = env.get("DEFAULT_FROM_EMAIL", "")
if old and frm.endswith("@" + old):
    upd["DEFAULT_FROM_EMAIL"] = frm[: -len(old)] + new
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
verify() {  # new old [www]
  local n="$1" o="${2:-}" w="${3:-0}" r i
  for i in 1 2 3 4 5; do r="$(probe "$n" "https://$n/api/v1/health/")"; [ "${r%% *}" = 200 ] && break; sleep 3; done
  [ "${r%% *}" = 200 ] || { echo "https://$n/api/v1/health/ answered ${r:-nothing}"; return 1; }
  if [ "$w" = 1 ]; then
    r="$(probe "www.$n" "https://www.$n/store?x=1")"
    [ "$r" = "301 https://$n/store?x=1" ] || { echo "https://www.$n does not redirect to $n (got: $r)"; return 1; }
    r="$(probe "www.$n" "http://www.$n/store")"
    [ "$r" = "301 https://$n/store" ] || { echo "http://www.$n does not redirect to $n (got: $r)"; return 1; }
  fi
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
  why="$(cert_check "$n" "$nw" "$MAIL")"
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
      if why="$(verify "$n" "$keep" "$nw")" && why="$(verify_mail "$n")"; then
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
  access) ACTION=access; BY=cli; do_access ;;
  retire) ACTION=retire; BY=cli; ID="$(sget change_id)"; do_retire ;;
  apply-request)
    [ -f "$REQ" ] || exit 0
    ACTION="$(jget "$REQ" action)"; ID="$(jget "$REQ" id)"; BY="$(jget "$REQ" requested_by)"
    D="$(jget "$REQ" domain)"; W="$(jget "$REQ" www)"; O="$(jget "$REQ" old_domain)"; DAYS="$(jget "$REQ" transition_days)"
    ZONE="$(jget "$REQ" zone)"; MAIL="$(jget "$REQ" mail)"; MAIL="${MAIL:-0}"
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
      access) do_access ;;
      dns01) do_dns01 ;;
      *) write_status 0 "rejected: unknown action"; die "unknown action $ACTION" ;;
    esac ;;
  *) sed -n '2,9p' "$0"; exit 2 ;;
esac
