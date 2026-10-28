#!/usr/bin/env bash
# End-to-end test of configurable admin / portal paths on a THROW-AWAY stack
# (copy of this tree, compose project "pathtest", own network, no published
# ports, images built under pathtest-* tags — production images untouched).
#   ./scripts/test-paths.sh
# default → set-admin → set-portal → panel request file → invalid request →
# failed verification rolls back → reset, with real nginx + browser checks.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d "${PATHTEST_DIR:-${TMPDIR:-/tmp}}/caspin-pathtest-XXXXXX")"
P=pathtest
FAILS=0
step() { printf '\n\033[1;35m### %s\033[0m\n' "$*"; }
check() { if eval "$2"; then printf '  \033[1;32mPASS\033[0m  %s\n' "$1"; else printf '  \033[1;31mFAIL\033[0m  %s\n' "$1"; FAILS=$((FAILS + 1)); fi; }
rnd() { head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "${1:-32}"; }
C="docker compose -p $P --project-directory $T -f $T/docker-compose.yml -f $T/docker-compose.prod.yml -f $T/docker-compose.pathtest.yml"
cleanup() {
  $C down -v --remove-orphans >/dev/null 2>&1 || true
  docker run --rm --network none -v "$T:/t" --entrypoint sh caspintunel-backend -c 'rm -rf /t/* /t/.[!.]*' >/dev/null 2>&1 || true
  rm -rf "$T"
  # the throw-away images too (~240 MB per run otherwise left behind)
  docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^pathtest-' | xargs -r docker rmi >/dev/null 2>&1 || true
}
trap cleanup EXIT

step "throw-away stack"
( cd "$ROOT" && git ls-files -co --exclude-standard -z | tar --null -T - -cf - ) | tar -xf - -C "$T"
sed -i "s/^name: caspintunel$/name: $P/" "$T/docker-compose.yml"
cat > "$T/docker-compose.pathtest.yml" <<'YML'
x-code: &code
  volumes:
    - ./backend:/app
services:
  web: *code
  daphne: *code
  nginx:
    image: pathtest-nginx
    ports: !reset []
  frontend_user:
    image: pathtest-frontend-user
    ports: !reset []
  frontend_admin:
    image: pathtest-frontend-admin
    ports: !reset []
YML
cat > "$T/.env" <<ENV
DOMAIN=pathtest.example
DJANGO_SETTINGS_MODULE=config.settings.prod
SECRET_KEY=$(rnd 50)
ALLOWED_HOSTS=pathtest.example,127.0.0.1,localhost,nginx
FIELD_ENCRYPTION_KEY=$(head -c 32 /dev/urandom | base64 | tr '+/' '-_')
DB_NAME=caspintunel
DB_USER=caspintunel
DB_PASSWORD=$(rnd 24)
DB_ROOT_PASSWORD=$(rnd 24)
DB_HOST=db
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
ENV
[ "$($C config --format json | python3 -c 'import json,sys;print(json.load(sys.stdin)["name"])')" = "$P" ] || { echo "not the throw-away project"; exit 1; }
docker build -q -t pathtest-nginx "$T/nginx" >/dev/null
docker build -q -t pathtest-frontend-admin "$T/frontend/admin" >/dev/null
docker build -q -t pathtest-frontend-user "$T/frontend/user" >/dev/null
$C up -d db redis >/dev/null 2>&1
for i in $(seq 1 60); do $C exec -T db sh -c 'mysqladmin ping -uroot -p"$MYSQL_ROOT_PASSWORD" --silent' >/dev/null 2>&1 && break; sleep 2; done; sleep 3
$C run --rm --no-deps -T web sh -c 'python manage.py migrate --noinput >/dev/null && python manage.py seed >/dev/null && python manage.py collectstatic --noinput >/dev/null'
mkdir -p "$T/backups" "$T/nginx/paths"
$C up -d --no-deps web daphne frontend_user frontend_admin nginx >/dev/null 2>&1
sleep 6
PS() { ( cd "$T" && PATHS_COMPOSE="$C" ./scripts/paths.sh "$@" ); }
get() { $C exec -T nginx wget -q -O - --header 'X-Forwarded-Proto: https' "http://127.0.0.1$1" 2>/dev/null || true; }
code() { $C exec -T nginx sh -c "wget -S -q -O /dev/null 'http://127.0.0.1$1' 2>&1 | grep -m1 -o 'HTTP/1.1 [0-9]*' | cut -d' ' -f2" 2>/dev/null; }
asset_of() { get "$1/" | grep -o 'src="./assets/[^"]*"' | head -1 | sed 's/src=".//; s/"$//'; }
browser() {  # browser JS → stdout JSON
  docker run --rm --network "${P}_default" --ipc=host -e NODE_PATH=/s/pw/node_modules -v /tmp/claude-0/-root-caspintunel/53956cd9-e7ad-4c1d-b55d-75ec110473bd/scratchpad:/s \
    mcr.microsoft.com/playwright:v1.49.1-noble node -e "$1" 2>/dev/null | tail -1
}
BROWSER_JS='
const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch(); const out = {}; const errs = [];
  for (const [k, url, sel] of JSON.parse(process.argv[1] || "[]")) {
    const p = await b.newPage(); p.on("pageerror", (e) => errs.push(k + ": " + e)); const bad = [];
    p.on("response", (r) => { if (r.status() >= 400 && /\.(js|css)$/.test(r.url())) bad.push(r.status() + " " + r.url()) });
    const resp = await p.goto("http://nginx" + url, { waitUntil: "networkidle" }).catch(() => null);
    await p.waitForTimeout(800);
    out[k] = { status: resp && resp.status(), final: new URL(p.url()).pathname, found: sel ? await p.$(sel) !== null : null, badAssets: bad,
               adminLinks: await p.$$eval("a", (as) => as.filter((a) => /panel/.test(a.getAttribute("href") || "")).length) };
    await p.close();
  }
  await b.close(); console.log(JSON.stringify({ out, errs }));
})();'
run_browser() { browser "process.argv[1]=$(printf '%s' "$1" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))'); $BROWSER_JS"; }

step "1. defaults (/panel, /agency)"
PS ensure >/dev/null
$C exec -T nginx nginx -s reload >/dev/null 2>&1; sleep 1
check "admin page on /panel/ with <base href=\"/panel/\">" 'get /panel/ | grep -q "<base href=\"/panel/\">"'
check "admin assets load from /panel/assets" '[ "$(code /panel/$(asset_of /panel))" = 200 ]'
check "user site announces portal /agency and the admin link" 'get / | grep -q "content=\"/agency\"><meta name=\"ct-admin-link\" content=\"/panel/\""'
R=$(run_browser '[["admin","/panel/agency/admins","form input[type=password]"],["portal","/agency/","form.ap-login"],["login","/login",null]]')
echo "  $R"
check "browser: deep admin link → login under /panel, no broken asset" 'echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin)[\"out\"][\"admin\"];sys.exit(0 if d[\"found\"] and d[\"final\"]==\"/panel/login\" and not d[\"badAssets\"] else 1)"'
check "browser: portal login form on /agency/" 'echo "$R" | python3 -c "import json,sys;sys.exit(0 if json.load(sys.stdin)[\"out\"][\"portal\"][\"found\"] else 1)"'

step "2. move the admin panel (CLI)"
PS set-admin /ctrl-x9
check "admin page on /ctrl-x9/ with <base href=\"/ctrl-x9/\">" 'get /ctrl-x9/ | grep -q "<base href=\"/ctrl-x9/\">"'
check "assets load under /ctrl-x9/assets" '[ "$(code /ctrl-x9/$(asset_of /ctrl-x9))" = 200 ]'
check "old /panel/ and /panel answer 404 (no redirect)" '[ "$(code /panel/)" = 404 ] && [ "$(code /panel/login)" = 404 ] && [ "$(code /panel)" = 404 ]'
check "user site no longer links to the admin panel" 'get / | grep -q "name=\"ct-admin-link\" content=\"\""'
check "admin keeps its locked-down CSP" '$C exec -T nginx sh -c "wget -S -q -O /dev/null http://127.0.0.1/ctrl-x9/ 2>&1" | grep -q "frame-ancestors '"'"'none'"'"'"'
R=$(run_browser '[["admin","/ctrl-x9/agency/admins","form input[type=password]"],["oldadmin","/panel/login","form input[type=password]"],["login","/login",null]]')
echo "  $R"
check "browser: panel works under /ctrl-x9 (deep link → /ctrl-x9/login, assets ok)" 'echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin)[\"out\"][\"admin\"];sys.exit(0 if d[\"found\"] and d[\"final\"]==\"/ctrl-x9/login\" and not d[\"badAssets\"] else 1)"'
check "browser: old /panel/login is a 404 page" 'echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin)[\"out\"][\"oldadmin\"];sys.exit(0 if d[\"status\"]==404 and not d[\"found\"] else 1)"'
check "browser: public login page shows no admin link" 'echo "$R" | python3 -c "import json,sys;sys.exit(0 if json.load(sys.stdin)[\"out\"][\"login\"][\"adminLinks\"]==0 else 1)"'

step "3. move the portal (request file, as the admin Settings page writes it)"
printf '{"admin": "/ctrl-x9", "portal": "/resellers", "requested_by": "boss"}' > "$T/backups/.paths-request.json"
PS apply-request
check "request consumed, status ok" '[ ! -f "$T/backups/.paths-request.json" ] && grep -q "\"ok\": true" "$T/backups/.paths-status.json"'
check "user site announces portal /resellers" 'get / | grep -q "name=\"ct-portal-path\" content=\"/resellers\""'
R=$(run_browser '[["portal","/resellers/","form.ap-login"],["oldportal","/agency/","form.ap-login"]]')
echo "  $R"
check "browser: portal on /resellers/, old /agency/ no longer the portal" 'echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin)[\"out\"];sys.exit(0 if d[\"portal\"][\"found\"] and not d[\"oldportal\"][\"found\"] else 1)"'

step "4. an invalid request changes nothing"
printf '{"admin": "/api", "portal": "/resellers", "requested_by": "x"}' > "$T/backups/.paths-request.json"
check "apply-request refuses /api" '! PS apply-request >/dev/null 2>&1'
check "status says rejected, panel still on /ctrl-x9" 'grep -q "rejected" "$T/backups/.paths-status.json" && get /ctrl-x9/ | grep -q "<base href=\"/ctrl-x9/\">"'

step "5. a change that fails verification is rolled back"
$C stop frontend_admin >/dev/null 2>&1
check "set-admin /other-x9 fails while the admin SPA is down" '! PS set-admin /other-x9 >/dev/null 2>&1'
check "rolled back: status says so, config still /ctrl-x9" 'grep -q "rolled back" "$T/backups/.paths-status.json" && grep -q "/ctrl-x9" "$T/nginx/paths/paths.json" && grep -q "admin=/ctrl-x9" "$T/nginx/paths/active.conf"'
$C start frontend_admin >/dev/null 2>&1; sleep 3
check "after the rollback the panel works on /ctrl-x9/ again" 'get /ctrl-x9/ | grep -q "<base href=\"/ctrl-x9/\">"'

step "6. reset"
PS reset
check "back on /panel/ and /agency" 'get /panel/ | grep -q "<base href=\"/panel/\">" && get / | grep -q "content=\"/agency\""'
check "/ctrl-x9/ is no longer the admin panel" '! get /ctrl-x9/ | grep -q "ct-admin-base"'
PS show

echo
if [ "$FAILS" = 0 ]; then echo "paths: ALL CHECKS PASSED"; else echo "paths: $FAILS CHECK(S) FAILED"; exit 1; fi
