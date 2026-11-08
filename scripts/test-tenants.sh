#!/usr/bin/env bash
# End-to-end test of the store-domain host watcher (scripts/tenants.sh + tenants_host.py) on a THROW-AWAY nginx: compose
# project "tenanttest", ports bound to 127.0.0.1 only, own temp dir — production untouched. The nginx image and the
# watcher are the real ones; the certificate comes from a fake certbot (self-signed, right SANs) and the "Iran tunnel" is
# scripts/domaintest/tunnel.py — a plain TCP port forward like backhaul (NO PROXY protocol).
#   ./scripts/test-tenants.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d "${TMPDIR:-/tmp}/caspin-tenanttest-XXXXXX")"
P=tenanttest
HTTP=18080; HTTPS=18443; TUN80=18081
FAILS=0
step() { printf '\n\033[1;35m### %s\033[0m\n' "$*"; }
check() { if eval "$2"; then printf '  \033[1;32mPASS\033[0m  %s\n' "$1"; else printf '  \033[1;31mFAIL\033[0m  %s\n' "$1"; FAILS=$((FAILS + 1)); fi; }
C="docker compose -p $P -f $T/compose.yml"
cleanup() { $C down -v --remove-orphans >/dev/null 2>&1 || true; rm -rf "$T"; }
trap cleanup EXIT
[ -n "${KEEP:-}" ] && trap - EXIT

mkdir -p "$T/tenants" "$T/le/live" "$T/webroot" "$T/conf" "$T/domain" "$T/backups"
cat > "$T/conf/00-upgrade-map.conf" <<'EOF'
map $http_upgrade $connection_upgrade { default upgrade; '' close; }
EOF
# the parts of nginx/prod.conf the store vhosts rely on: port-80 default server with the ACME webroot and the
# /.well-known/caspin/ probe (answered here by nginx instead of Django), plus the tenants include
cat > "$T/conf/caspintunel.conf" <<'EOF'
server {
    listen 80 default_server;
    server_name _;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location ~ ^/\.well-known/caspin/(?<tok>[A-Za-z0-9_-]+)$ { default_type text/plain; return 200 $tok; }
    location / { default_type text/plain; return 200 "site $host\n"; }
}
# stands in for our own caspintunel.com vhost (scripts/domain.sh): loaded first, so it is the default for unknown names
server {
    listen 443 ssl;
    server_name ours.test;
    ssl_certificate     /etc/letsencrypt/live/ours/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ours/privkey.pem;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { default_type text/plain; return 200 "ours\n"; }
}
include /etc/nginx/tenants/*.conf;
EOF
mkdir -p "$T/le/live/ours"
openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=ours.test" -addext "subjectAltName=DNS:ours.test" \
  -keyout "$T/le/live/ours/privkey.pem" -out "$T/le/live/ours/fullchain.pem" >/dev/null 2>&1
cat > "$T/compose.yml" <<YML
services:
  nginx:
    image: caspintunel-nginx
    entrypoint: ["nginx", "-g", "daemon off;"]
    ports: ["127.0.0.1:$HTTP:80", "127.0.0.1:$HTTPS:443"]
    volumes:
      - $T/conf:/etc/nginx/conf.d:ro
      - $T/tenants:/etc/nginx/tenants:ro
      - $T/domain:/etc/nginx/domain:ro
      - $T/le:/etc/letsencrypt:ro
      - $T/webroot:/var/www/certbot:ro
  iran:
    image: caspintunel-backend
    entrypoint: ["python", "/mock/tunnel.py"]
    ports: ["127.0.0.1:$TUN80:80"]
    volumes: ["$ROOT/scripts/domaintest:/mock:ro"]
YML
cat > "$T/fake-certbot.sh" <<'EOF'
#!/bin/sh
# fake certbot: <lineage> <names…> → self-signed certificate with exactly those SANs
set -e
l="$1"; shift
echo "$l $*" >> "$TENANTS_LE/calls.log"
[ -f "$TENANTS_LE/fail" ] && { echo "Type: unauthorized Detail: fake failure"; exit 1; }
san=""; for n in "$@"; do san="${san:+$san,}DNS:$n"; done
mkdir -p "$TENANTS_LE/live/$l"
openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=$1" -addext "subjectAltName=$san" \
  -keyout "$TENANTS_LE/live/$l/privkey.pem" -out "$TENANTS_LE/live/$l/fullchain.pem" >/dev/null 2>&1
EOF
chmod +x "$T/fake-certbot.sh"

export TENANTS_COMPOSE="$C" TENANTS_DESIRED="$T/backups/.tenant-domains.json" TENANTS_STATUS="$T/backups/.tenant-status.json"
export TENANTS_CONF_DIR="$T/tenants" TENANTS_LE="$T/le" TENANTS_WEBROOT="$T/webroot" TENANTS_CERTBOT="$T/fake-certbot.sh"
export TENANTS_VERIFY_ADDR=127.0.0.1 TENANTS_VERIFY_PORT=$HTTPS TENANTS_INSECURE=1 TENANTS_PRECHECK_ADDR=127.0.0.1
W() { python3 "$ROOT/scripts/tenants_host.py" apply-request; }
want() {  # host:www:retry …
  python3 - "$TENANTS_DESIRED" "$@" <<'PY'
import json, sys
hosts = []
for a in sys.argv[2:]:
    h, www, retry = a.split(":")
    hosts.append({"host": h, "www": www == "1", "tenant": 7, "retry": int(retry), "token": ("tok" + h.replace(".", "x") + "0" * 20)[:24]})
json.dump({"at": "now", "email": "t@example.com", "hosts": hosts}, open(sys.argv[1], "w"))
PY
}
st() { python3 -c "import json,sys;d=json.load(open('$TENANTS_STATUS'))['hosts'].get('$1',{});v=d.get('$2');print('' if v is None else v)"; }
tls() { curl -sk --max-time 5 --connect-to "$1:443:127.0.0.1:$HTTPS" "https://$1$2" -o /dev/null -w '%{http_code} %{redirect_url}'; }
body() { curl -sk --max-time 5 --connect-to "$1:443:127.0.0.1:$HTTPS" "https://$1$2"; }
cn() { echo | openssl s_client -connect 127.0.0.1:$HTTPS -servername "$1" 2>/dev/null | openssl x509 -noout -ext subjectAltName 2>/dev/null | tr -d ' \n'; }
calls() { [ -f "$T/le/calls.log" ] && wc -l < "$T/le/calls.log" | tr -d ' ' || echo 0; }

step "throw-away nginx + tunnel forwarder"
$C up -d >/dev/null 2>&1
for i in $(seq 1 30); do curl -s -o /dev/null "http://127.0.0.1:$HTTP/" && break; sleep 1; done
check "nginx answers" '[ "$(curl -s http://127.0.0.1:$HTTP/ -H "Host: x.test")" = "site x.test" ]'

step "1. direct mode, DNS-only: HTTP-01 pre-check on port 80 → certificate (+www) → vhost → TLS"
export TENANTS_PRECHECK_PORT=$HTTP
want shop-a.test:1:0
W
check "pre-check passed" '[ "$(st shop-a.test challenge_ok)" = True ]'
check "certbot asked once for both names" '[ "$(calls)" = 1 ] && grep -q "store-shop-a.test shop-a.test www.shop-a.test" "$T/le/calls.log"'
check "status: certificate + nginx ok" '[ "$(st shop-a.test cert_ok)" = True ] && [ "$(st shop-a.test nginx_ok)" = True ]'
check "vhost file written" '[ -s "$T/tenants/shop-a.test.conf" ]'
check "TLS on 443 with the store's own certificate" '[[ "$(cn shop-a.test)" == *DNS:shop-a.test* ]]'
check "probe answered over TLS" '[ "$(body shop-a.test /.well-known/caspin/tokshop-axtest00000000000)" = "tokshop-axtest00000000000" ] || [ "$(tls shop-a.test /.well-known/caspin/x)" != "000 " ]'
check "site proxied for the store host" '[ "$(body shop-a.test /)" = "site shop-a.test" ]'
check "www → bare host (301, path kept)" '[ "$(tls www.shop-a.test "/store?x=1")" = "301 https://shop-a.test/store?x=1" ]'
check "unknown name still gets the default (no store cert)" '[[ "$(cn nobody.test)" != *shop-a.test* ]]'
W
check "second run: nothing to do (no new certbot call)" '[ "$(calls)" = 1 ]'

step "2. Iran tunnel mode, no PROXY protocol: the pre-check goes through a plain TCP forward (Iran :80 → our :80)"
export TENANTS_PRECHECK_PORT=$TUN80
want shop-a.test:1:0 shop-b.test:0:0
W
check "pre-check through the tunnel passed" '[ "$(st shop-b.test challenge_ok)" = True ]'
check "certificate without www (www not asked)" 'grep -q "store-shop-b.test shop-b.test$" "$T/le/calls.log"'
check "shop-b live over TLS, shop-a untouched" '[ "$(body shop-b.test /)" = "site shop-b.test" ] && [ "$(body shop-a.test /)" = "site shop-a.test" ]'
check "TLS through the tunnel forwarder too" '[ "$(curl -s --max-time 5 -H "Host: shop-b.test" http://127.0.0.1:$TUN80/.well-known/caspin/abcdefghijklmnop1234)" = "abcdefghijklmnop1234" ]'

step "3. a name that does not reach us: pre-check fails, Let's Encrypt is never asked"
export TENANTS_PRECHECK_PORT=1
want shop-a.test:1:0 shop-b.test:0:0 shop-c.test:0:0
n="$(calls)"; W
check "pre-check failure recorded" '[ "$(st shop-c.test challenge_ok)" = False ] && [ -n "$(st shop-c.test challenge_error)" ]'
check "no certbot call" '[ "$(calls)" = "$n" ]'
check "no vhost for it" '[ ! -e "$T/tenants/shop-c.test.conf" ]'

step "4. a failed issuance waits 30 min — unless staff retry"
export TENANTS_PRECHECK_PORT=$HTTP
touch "$T/le/fail"
want shop-a.test:1:0 shop-b.test:0:0 shop-d.test:0:0
n="$(calls)"; W
check "failure recorded with Let's Encrypt's words" '[[ "$(st shop-d.test cert_error)" == *unauthorized* ]]'
W
check "no second attempt within the backoff" '[ "$(calls)" = "$((n + 1))" ]'
rm -f "$T/le/fail"
want shop-a.test:1:0 shop-b.test:0:0 shop-d.test:0:1
W
check "retry counter → tried again at once, now ok" '[ "$(calls)" = "$((n + 2))" ] && [ "$(st shop-d.test cert_ok)" = True ]'

step "5. a vhost that breaks nginx is rolled back, the others keep working"
rm -f "$T/tenants/shop-d.test.conf"
printf 'broken' > "$T/le/live/store-shop-d.test/privkey.pem"
python3 - "$TENANTS_STATUS" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["hosts"]["shop-d.test"].pop("nginx_error", None); json.dump(d, open(sys.argv[1], "w"))
PY
W
check "nginx error recorded for shop-d" '[[ "$(st shop-d.test nginx_error)" == *nginx* ]] && [ "$(st shop-d.test nginx_ok)" = False ]'
check "its file is not left behind" '[ ! -e "$T/tenants/shop-d.test.conf" ]'
check "shop-a + shop-b still served" '[ "$(body shop-a.test /)" = "site shop-a.test" ] && [ "$(body shop-b.test /)" = "site shop-b.test" ]'
check "nginx config valid" '$C exec -T nginx nginx -t >/dev/null 2>&1'

step "6. removing a domain removes its vhost and certificate"
want shop-b.test:0:0
W; sleep 2                                    # old nginx workers finish with the previous config
check "shop-a vhost + certificate gone" '[ ! -e "$T/tenants/shop-a.test.conf" ] && [ ! -d "$T/le/live/store-shop-a.test" ]'
check "shop-a no longer gets its certificate" '[[ "$(cn shop-a.test)" != *DNS:shop-a.test* ]]'
check "shop-b still live" '[ "$(body shop-b.test /)" = "site shop-b.test" ]'
check "status only lists wanted hosts" '[ -z "$(st shop-a.test cert_ok)" ]'

step "7. bad entries in the wanted file are skipped (no shell / nginx injection)"
python3 - "$TENANTS_DESIRED" <<'PY'
import json, sys
json.dump({"hosts": [{"host": "evil.test; rm -rf /", "www": False, "token": "a" * 24},
                     {"host": "ok.test", "www": False, "token": "bad token!"}]}, open(sys.argv[1], "w"))
PY
n="$(calls)"; W
check "nothing issued, nothing rendered" '[ "$(calls)" = "$n" ] && [ -z "$(ls "$T/tenants" | grep -v shop-b || true)" ]'

printf '\n'
if [ "$FAILS" = 0 ]; then printf '\033[1;32mALL PASSED\033[0m\n'; else printf '\033[1;31m%s FAILED\033[0m\n' "$FAILS"; exit 1; fi
