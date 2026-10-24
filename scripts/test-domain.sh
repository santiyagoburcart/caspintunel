#!/usr/bin/env bash
# End-to-end test of the domain wizard on a THROW-AWAY stack (copy of this tree,
# compose project "domaintest", own network, no published ports, images under
# domaintest-* tags — production untouched). Fake domains old.test → new.test,
# a mock Cloudflare API + DNS-over-HTTPS (scripts/domaintest/cfmock.py) and a
# fake certbot (self-signed, scripts/domaintest/fake-certbot.sh); everything
# else is real: the admin API, scripts/domain.sh, nginx, .env, rolling restart.
#   ./scripts/test-domain.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d "${DOMAINTEST_DIR:-${TMPDIR:-/tmp}}/caspin-domaintest-XXXXXX")"
P=domaintest
FAILS=0
step() { printf '\n\033[1;35m### %s\033[0m\n' "$*"; }
check() { if eval "$2"; then printf '  \033[1;32mPASS\033[0m  %s\n' "$1"; else printf '  \033[1;31mFAIL\033[0m  %s\n' "$1"; FAILS=$((FAILS + 1)); fi; }
rnd() { head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "${1:-32}"; }
C="docker compose -p $P --project-directory $T -f $T/docker-compose.yml -f $T/docker-compose.prod.yml -f $T/docker-compose.domaintest.yml"
cleanup() {
  $C down -v --remove-orphans >/dev/null 2>&1 || true
  docker run --rm --network none -v "$T:/t" --entrypoint sh caspintunel-backend -c 'rm -rf /t/* /t/.[!.]*' >/dev/null 2>&1 || true
  rm -rf "$T"
}
trap cleanup EXIT
CF_TOKEN=mock-cloudflare-token-0123456789abcdef
IP=203.0.113.10

step "throw-away stack (old.test)"
( cd "$ROOT" && git ls-files -co --exclude-standard -z | tar --null -T - -cf - ) | tar -xf - -C "$T"
sed -i "s/^name: caspintunel$/name: $P/" "$T/docker-compose.yml"
cat > "$T/docker-compose.domaintest.yml" <<'YML'
x-code: &code
  volumes:
    - ./backend:/app
    - ./backups:/app/backups
services:
  web: *code
  daphne: *code
  nginx:
    image: domaintest-nginx
    ports: !reset []
  frontend_user:
    image: domaintest-frontend-user
    ports: !reset []
  frontend_admin:
    image: domaintest-frontend-admin
    ports: !reset []
  mailserver:
    ports: !reset []
  cfmock:
    image: caspintunel-backend
    entrypoint: ["python", "/mock/cfmock.py"]
    volumes:
      - ./scripts/domaintest:/mock:ro
YML
cat > "$T/.env" <<ENV
DOMAIN=old.test
DJANGO_SETTINGS_MODULE=config.settings.prod
SECRET_KEY=$(rnd 50)
ALLOWED_HOSTS=old.test,www.old.test,127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=https://old.test,https://www.old.test
PUBLIC_BASE_URL=https://old.test
DEFAULT_FROM_EMAIL=no-reply@old.test
MINIAPP_URL=
SERVER_IP=$IP
FIELD_ENCRYPTION_KEY=$(head -c 32 /dev/urandom | base64 | tr '+/' '-_')
CLOUDFLARE_API_BASE=http://cfmock:8080/client/v4
DOMAIN_DOH_URLS=http://cfmock:8080/dns-query
DB_NAME=caspintunel
DB_USER=caspintunel
DB_PASSWORD=$(rnd 24)
DB_ROOT_PASSWORD=$(rnd 24)
DB_HOST=db
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
ENV
[ "$($C config --format json | python3 -c 'import json,sys;print(json.load(sys.stdin)["name"])')" = "$P" ] || { echo "not the throw-away project"; exit 1; }
mkdir -p "$T/backups" "$T/nginx/paths" "$T/nginx/domain" "$T/nginx/letsencrypt"
export FAKE_LE="$T/nginx/letsencrypt"
"$T/scripts/domaintest/fake-certbot.sh" old.test -d old.test -d www.old.test >/dev/null     # today's LE cert
docker build -q -t domaintest-nginx "$T/nginx" >/dev/null
docker build -q -t domaintest-frontend-admin "$T/frontend/admin" >/dev/null
docker build -q -t domaintest-frontend-user "$T/frontend/user" >/dev/null
$C up -d db redis cfmock >/dev/null 2>&1
for i in $(seq 1 60); do $C exec -T db sh -c 'mysqladmin ping -uroot -p"$MYSQL_ROOT_PASSWORD" --silent' >/dev/null 2>&1 && break; sleep 2; done; sleep 3
$C run --rm --no-deps -T web sh -c 'python manage.py migrate --noinput >/dev/null && python manage.py seed >/dev/null && python manage.py collectstatic --noinput >/dev/null'
( cd "$T" && ./scripts/paths.sh ensure >/dev/null ) || true
$C up -d --no-deps web daphne frontend_user frontend_admin nginx mailserver >/dev/null 2>&1
for i in $(seq 1 60); do [ "$(docker inspect -f '{{.State.Health.Status}}' "$($C ps -q web)" 2>/dev/null)" = healthy ] && break; sleep 2; done
for i in $(seq 1 60); do [ "$(docker inspect -f '{{.State.Health.Status}}' "$($C ps -q mailserver)" 2>/dev/null)" = healthy ] && break; sleep 3; done
TOK=$($C exec -T web python manage.py shell -c "
from apps.accounts.models import Staff
from apps.adminpanel.tokens import issue_tokens
s = Staff(username='boss', is_superadmin=True); s.set_password('x-Str0ng-Pass'); s.save()
print(issue_tokens(s)['access'])" 2>/dev/null | tail -1)
HOST=old.test
API() {  # METHOD PATH [json] → body (Django directly, as nginx would forward an HTTPS request)
  $C exec -T web curl -s -X "$1" -H "Authorization: Bearer $TOK" -H "Host: $HOST" -H 'X-Forwarded-Proto: https' \
    -H 'Content-Type: application/json' ${3:+--data "$3"} "http://127.0.0.1:8000/api/v1/admin$2"
}
J() { python3 -c "import json,sys;d=json.load(sys.stdin);print(eval(sys.argv[1]))" "$1"; }
HOSTRUN() { ( cd "$T" && DOMAIN_COMPOSE="$C" DOMAIN_CERTBOT="$T/scripts/domaintest/fake-certbot.sh" DOMAIN_APP_OTHERS="mailserver" ./scripts/domain.sh "$@" ); }
probe() {  # host url → "code redirect" through nginx, like domain.sh verifies
  local ip; ip="$($C exec -T web getent hosts nginx | awk 'NR==1{print $1}')"
  local port=443; case "$2" in http://*) port=80 ;; esac
  $C exec -T web curl -sk -o /dev/null -w '%{http_code} %{redirect_url}' ${3:+-X $3} --resolve "$1:$port:$ip" "$2" 2>/dev/null || true
}
cert_cn() { local ip; ip="$($C exec -T web getent hosts nginx | awk 'NR==1{print $1}')"
  echo | openssl s_client -connect "$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$($C ps -q nginx)"):443" -servername "$1" 2>/dev/null | openssl x509 -noout -subject 2>/dev/null; }
cf_records() { $C exec -T web curl -s http://cfmock:8080/records | python3 -c 'import json,sys;print(" ".join(sorted("%s=%s/%s" % (r["name"], r["content"], r["proxied"]) for r in json.load(sys.stdin))))'; }
mail_host() { $C exec -T mailserver postconf -h myhostname 2>/dev/null | tr -d '\r'; }
mail_cert() {  # SAN of the certificate the mail server offers on STARTTLS
  echo QUIT | timeout 20 openssl s_client -connect "$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$($C ps -q mailserver)"):25" \
    -starttls smtp 2>/dev/null | openssl x509 -noout -ext subjectAltName 2>/dev/null | tr -d ' \n'; }
mail_recs() { $C exec -T web curl -s http://cfmock:8080/records | python3 -c 'import json,sys;print(" ".join(sorted("%s:%s" % (r["type"], r["name"]) for r in json.load(sys.stdin) if r["type"] != "A")))'; }
envv() { grep -E "^$1=" "$T/.env" | cut -d= -f2-; }
check "mail server up as mail.old.test" '[ "$(mail_host)" = mail.old.test ]'
check "stack serves https://old.test (TLS + health)" '[ "$(probe old.test https://old.test/api/v1/health/)" = "200 " ]'
check "super admin token works" '[ "$(API GET /domain/ | J "d[\"current\"][\"domain\"]")" = old.test ]'

step "1. Cloudflare token (saved encrypted, tested)"
API POST /domain/token/ "{\"token\": \"$CF_TOKEN\"}" >/dev/null
check "API never returns the token" '! API GET /domain/ | grep -q "$CF_TOKEN"'
check "stored encrypted in the DB" '$C exec -T db sh -c "mysql -N -uroot -p\"\$MYSQL_ROOT_PASSWORD\" caspintunel -e \"select cloudflare_token from domain_config\"" 2>/dev/null | grep -q "^enc:v1:"'
R=$(API POST /domain/token/test/ '{}')
check "test: ok, 3 zones, view-only zone flagged" '[ "$(echo "$R" | J "[d[\"ok\"], len(d[\"zones\"]), [z[\"dns_edit\"] for z in d[\"zones\"]]]")" = "[True, 3, [True, True, False]]" ]'
check "test: per zone can read / can edit DNS (real write + delete)" '[ "$(echo "$R" | J "[[z[\"read\"], z[\"dns_edit\"]] for z in d[\"zones\"]]")" = "[[True, True], [True, True], [True, False]]" ]'
check "test: view-only zone says how to fix it (fa + raw code)" '[ "$(echo "$R" | J "d[\"zones\"][2][\"error\"][\"key\"] + \" \" + d[\"zones\"][2][\"error\"][\"raw\"]")" = "cf_perm 10000: Authentication error" ] && echo "$R" | J "d[\"zones\"][2][\"error\"][\"fa\"]" | grep -q "Zone Resources شامل view-only.test"'
check "test: temporary TXT records were deleted again" '! $C exec -T web curl -s http://cfmock:8080/records | grep -q _caspintunel-check'
R=$(API POST /domain/token/test/ '{"token": "wrong-token-0000000000000000"}')
check "test with a wrong token: clear error + raw code" '[ "$(echo "$R" | J "d[\"explain\"][\"key\"]")" = cf_invalid ] && echo "$R" | J "d[\"explain\"][\"raw\"]" | grep -q "9109: Invalid access token" && echo "$R" | J "d[\"error_fa\"]" | grep -q "API Tokens"'

step "2a. a zone the token may only read: checked before step 2, nothing written"
R=$(API POST /domain/start/ '{"domain": "view-only.test", "include_www": false, "mode": "cloudflare"}')
VID=$(echo "$R" | J 'd["change"]["id"]')
R=$(API POST "/domain/$VID/dns/")
check "DNS step refused: cf_perm naming the zone, raw 10000" '[ "$(echo "$R" | J "d[\"error\"][\"key\"] + \" \" + d[\"error\"][\"raw\"]")" = "cf_perm 10000: Authentication error" ] && echo "$R" | J "d[\"detail_fa\"]" | grep -q "در دامنهٔ view-only.test را ندارد"'
check "step shows the zone check (read yes, edit no)" '[ "$(echo "$R" | J "\" \".join(map(str, [d[\"change\"][\"steps\"][\"dns\"][\"state\"], d[\"change\"][\"steps\"][\"dns\"][\"detail\"][\"zone_check\"][\"read\"], d[\"change\"][\"steps\"][\"dns\"][\"detail\"][\"zone_check\"][\"dns_edit\"]]))")" = "failed True False" ]'
check "no record written in view-only.test" '! $C exec -T web curl -s http://cfmock:8080/records | grep -q view-only.test'
API POST "/domain/$VID/cancel/" >/dev/null

step "2. wizard: start → DNS via Cloudflare → resolves"
R=$(API POST /domain/start/ '{"domain": "new.test", "include_www": true, "mode": "cloudflare"}')
CID=$(echo "$R" | J 'd["change"]["id"]')
check "change started for new.test in zone new.test" '[ "$(echo "$R" | J "d[\"change\"][\"zone_name\"]")" = new.test ]'
R=$(API POST "/domain/$CID/dns/")
check "A records root/www/mail created in Cloudflare (DNS-only, this IP)" '[ "$(cf_records)" = "mail.new.test=$IP/False new.test=$IP/False www.new.test=$IP/False" ]'
check "DNS step ok (public DNS answers this server)" '[ "$(echo "$R" | J "d[\"change\"][\"steps\"][\"dns\"][\"state\"]")" = ok ]'

step "3. TLS through the host watcher"
API POST "/domain/$CID/tls/" >/dev/null
check "request file written for the host" '[ "$(J "d[\"action\"]" < "$T/backups/.domain-request.json")" = cert ]'
HOSTRUN apply-request
check "certificate covers new.test + www" 'openssl x509 -in "$FAKE_LE/live/new.test/fullchain.pem" -noout -ext subjectAltName | grep -q "DNS:www.new.test"'
check "certificate covers mail.new.test too" 'openssl x509 -in "$FAKE_LE/live/new.test/fullchain.pem" -noout -ext subjectAltName | grep -q "DNS:mail.new.test"'
check "DKIM key made by the mail server (selector mail, in its KeyTable)" '$C exec -T mailserver test -s /tmp/docker-mailserver/opendkim/keys/new.test/mail.private && $C exec -T mailserver grep -q "mail._domainkey.new.test" /tmp/docker-mailserver/opendkim/KeyTable && grep -q "v=DKIM1" "$T/backups/.domain-dkim.json"'
R=$(API GET /domain/)
check "mail records published in Cloudflare: MX, SPF, DMARC, DKIM" '[ "$(mail_recs)" = "MX:new.test TXT:_dmarc.new.test TXT:mail._domainkey.new.test TXT:new.test" ]'
check "mail step ok (public DNS answers them, DKIM = the server key)" '[ "$(echo "$R" | J "d[\"change\"][\"steps\"][\"mail\"][\"state\"]")" = ok ] && echo "$R" | J "d[\"change\"][\"mail_records\"][3][\"content\"]" | grep -q "$(python3 -c "import json;print(json.load(open(\"$T/backups/.domain-dkim.json\"))[\"txt\"][-40:])")"'
check "TLS step ok in the wizard" '[ "$(API GET /domain/ | J "d[\"change\"][\"steps\"][\"tls\"][\"state\"]")" = ok ]'

step "4. apply: nginx + .env + rolling restart + verify"
API POST "/domain/$CID/apply/" >/dev/null
OLDWEB=$($C ps -q web)
HOSTRUN apply-request
check "https://new.test answers (health 200) with the new certificate" '[ "$(probe new.test https://new.test/api/v1/health/)" = "200 " ] && cert_cn new.test | grep -q "CN *= *new.test"'
check "https://old.test → 301 https://new.test (path + query kept)" '[ "$(probe old.test "https://old.test/store?a=1")" = "301 https://new.test/store?a=1" ]'
check "http://www.old.test → 301 https://new.test" '[ "$(probe www.old.test http://www.old.test/x)" = "301 https://new.test/x" ]'
check "POST to the old domain → 308 (method + body kept)" '[ "$(probe old.test https://old.test/api/v1/sms/ POST)" = "308 https://new.test/api/v1/sms/" ]'
check ".env: DOMAIN, PUBLIC_BASE_URL, hosts + CSRF (old kept)" '[ "$(envv DOMAIN)" = new.test ] && [ "$(envv PUBLIC_BASE_URL)" = https://new.test ] && envv ALLOWED_HOSTS | grep -q "old.test.*new.test,www.new.test" && envv CSRF_TRUSTED_ORIGINS | grep -q "https://new.test,https://www.new.test"'
check "mail server moved: mail.new.test, STARTTLS cert covers mail.new.test" '[ "$(mail_host)" = mail.new.test ] && mail_cert | grep -q "DNS:mail.new.test"'
check ".env: MAIL_DOMAIN=new.test, sender no-reply@new.test" '[ "$(envv MAIL_DOMAIN)" = new.test ] && [ "$(envv DEFAULT_FROM_EMAIL)" = no-reply@new.test ]'
check "web was replaced (rolling) and runs with the new DOMAIN" '[ "$($C ps -q web)" != "$OLDWEB" ] && [ "$($C exec -T web printenv DOMAIN)" = new.test ]'
HOST=new.test
R=$(API GET /domain/)
check "wizard: transition, links ok, site URL new.test, rollback offered" '[ "$(echo "$R" | J "\" \".join([d[\"change\"][\"status\"], d[\"change\"][\"steps\"][\"links\"][\"state\"], d[\"current\"][\"site_domain\"], d[\"rollback\"][\"to\"]])")" = "transition ok new.test old.test" ]'
check "nginx restart keeps the new domain (entrypoint uses the wizard config)" '$C restart nginx >/dev/null 2>&1; sleep 2; [ "$(probe new.test https://new.test/api/v1/health/)" = "200 " ] && [ "$(probe old.test https://old.test/)" = "301 https://new.test/" ]'

step "5. remove the old domain (transition over)"
API POST "/domain/$CID/retire/" >/dev/null
HOSTRUN apply-request
check "old.test no longer redirects; new.test fine" '[ "$(probe old.test http://old.test/x | cut -d" " -f1)" != 301 ] && [ "$(probe new.test https://new.test/api/v1/health/)" = "200 " ]'
check ".env: old.test left ALLOWED_HOSTS / CSRF" '! envv ALLOWED_HOSTS | grep -q "old.test" && ! envv CSRF_TRUSTED_ORIGINS | grep -q old.test'
check "wizard: done" '[ "$(API GET /domain/ | J "d[\"change\"][\"status\"]")" = done ]'

step "6. one-click rollback (panel) → old.test"
API POST /domain/rollback/ >/dev/null
HOSTRUN apply-request
HOST=old.test
check "mail back on mail.old.test, MAIL_DOMAIN=old.test" '[ "$(mail_host)" = mail.old.test ] && [ "$(envv MAIL_DOMAIN)" = old.test ]'
check "back on https://old.test, .env DOMAIN=old.test" '[ "$(probe old.test https://old.test/api/v1/health/)" = "200 " ] && [ "$(envv DOMAIN)" = old.test ]'
R=$(API GET /domain/)
check "wizard: rolled back, site URL old.test" '[ "$(echo "$R" | J "\" \".join([d[\"change\"][\"status\"], d[\"current\"][\"site_domain\"]])")" = "rolled_back old.test" ]'

step "7. a switch that fails is rolled back automatically"
R=$(API POST /domain/start/ '{"domain": "bad.test", "include_www": false, "mode": "cloudflare"}')
BID=$(echo "$R" | J 'd["change"]["id"]')
API POST "/domain/$BID/dns/" >/dev/null
API POST "/domain/$BID/tls/" >/dev/null
FAKE_CERT_BADKEY=1 HOSTRUN apply-request >/dev/null 2>&1 || true      # cert ok, key does not match → nginx -t fails
API POST "/domain/$BID/apply/" >/dev/null
check "apply-request reports failure" '! HOSTRUN apply-request >/dev/null 2>&1'
check "status says rolled back with the real reason" 'grep -q "rolled back to old.test: nginx -t rejected" "$T/backups/.domain-status.json"'
check "mail server restored to mail.old.test" '[ "$(mail_host)" = mail.old.test ]'
check "site still on old.test, .env unchanged" '[ "$(probe old.test https://old.test/api/v1/health/)" = "200 " ] && [ "$(envv DOMAIN)" = old.test ] && ! envv ALLOWED_HOSTS | grep -q bad.test'
R=$(API GET /domain/)
check "wizard: back to draft, apply failed with the reason" '[ "$(echo "$R" | J "\" \".join([d[\"change\"][\"status\"], d[\"change\"][\"steps\"][\"apply\"][\"state\"]])")" = "draft failed" ]'
check "apply error explained: nginx_test + the nginx error in details" '[ "$(echo "$R" | J "d[\"change\"][\"steps\"][\"apply\"][\"detail\"][\"error\"][\"key\"]")" = nginx_test ] && echo "$R" | J "d[\"change\"][\"steps\"][\"apply\"][\"detail\"][\"error\"][\"raw\"]" | grep -qiE "rejected the config: .*(emerg|fail|error)"'
API POST "/domain/$BID/cancel/" >/dev/null

step "8. recovery CLI"
HOSTRUN show
HOSTRUN rollback >/dev/null
check "./scripts/domain.sh rollback → previous domain (new.test)" '[ "$(probe new.test https://new.test/api/v1/health/)" = "200 " ] && [ "$(envv DOMAIN)" = new.test ]'
check "audit log has every step" '[ "$(API GET /domain/ >/dev/null; $C exec -T db sh -c "mysql -N -uroot -p\"\$MYSQL_ROOT_PASSWORD\" caspintunel -e \"select count(distinct action) from audit_log where action like \\\"domain.%\\\"\"" 2>/dev/null)" -ge 15 ]'

echo
if [ "$FAILS" = 0 ]; then echo "domain: ALL CHECKS PASSED"; else echo "domain: $FAILS CHECK(S) FAILED"; exit 1; fi
