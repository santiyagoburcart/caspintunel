#!/usr/bin/env bash
# Live preview of THIS checkout's frontends next to the production site:
#   https://<domain>/preview/        user site
#   https://<domain>/preview-panel/  admin panel
# Both use the LIVE API (real data, real actions) and show a "preview" banner.
# The live / and /panel/ are not touched: the preview is served by its own
# container (caspintunel-preview) and routed by two extra locations included in
# the running nginx's TLS vhost (no change to any tracked nginx config).
#
#   ./scripts/preview.sh build    build both SPAs for the preview paths
#   ./scripts/preview.sh up       (re)start the container + nginx routes
#   ./scripts/preview.sh update   build + up (use after every change)
#   ./scripts/preview.sh status   what is running / routed
#   ./scripts/preview.sh remove   take the preview down completely
#
# The nginx route lives inside the nginx container (its TLS vhost is generated
# at container start), so after the live nginx container is recreated/restarted
# just run `./scripts/preview.sh up` again. The live site is unaffected either way.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIVE="${LIVE_DIR:-/root/caspintunel}"            # the production checkout (compose project)
OUT="${PREVIEW_DIR:-/root/caspintunel-preview}"  # built files + container config
NAME=caspintunel-preview
NET=caspintunel_default
LIVE_COMPOSE=(docker compose --project-directory "$LIVE" -f "$LIVE/docker-compose.yml" -f "$LIVE/docker-compose.prod.yml")
INC=/etc/nginx/preview.inc
SSL=/etc/nginx/conf.d/10-ssl.conf

build() {
  echo "==> palettes (backend/apps/settings_app/theme_palettes.json → both SPAs)"
  for app in user admin; do
    cp "$ROOT/backend/apps/settings_app/theme_palettes.json" "$ROOT/frontend/$app/src/theme/preview-palettes.json"
  done
  rm -rf "$OUT/html.new"; mkdir -p "$OUT/html.new"
  for app in user admin; do
    local base; [ "$app" = user ] && base=/preview/ || base=/preview-panel/
    echo "==> build $app → $base"
    ( cd "$ROOT/frontend/$app"
      [ -d node_modules ] && [ node_modules/.package-lock.json -nt package-lock.json ] || npm ci --no-audit --no-fund --loglevel=error
      VITE_BASE=$base VITE_PREVIEW=1 VITE_USER_URL=/preview/ VITE_ADMIN_URL=/preview-panel/ \
        npx vite build --logLevel warn --outDir "$OUT/html.new${base%/}" --emptyOutDir )
  done
  rm -rf "$OUT/html.old"; [ -d "$OUT/html" ] && mv "$OUT/html" "$OUT/html.old"
  mv "$OUT/html.new" "$OUT/html"; rm -rf "$OUT/html.old"
  echo "   built: $(du -sh "$OUT/html" | cut -f1)"
}

container() {
  cat > "$OUT/nginx.conf" <<'CONF'
server {
    listen 80;
    # the parent dir is mounted so an atomic swap of html/ is seen at once
    root /srv/preview/html;
    # hashed bundles can be cached; index.html never (so a rebuild shows at once)
    location ~ ^/(preview|preview-panel)/assets/ { expires 7d; access_log off; }
    location /preview-panel/ { try_files $uri $uri/ /preview-panel/index.html; add_header Cache-Control "no-cache"; }
    location /preview/       { try_files $uri $uri/ /preview/index.html;       add_header Cache-Control "no-cache"; }
    location / { return 404; }
}
CONF
  if docker ps --format '{{.Names}}' | grep -qx "$NAME" \
     && docker inspect -f '{{range .Mounts}}{{.Destination}} {{end}}' "$NAME" | grep -q '/srv/preview'; then
    docker exec "$NAME" nginx -s reload >/dev/null
  else
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    docker run -d --name "$NAME" --network "$NET" --restart unless-stopped \
      -v "$OUT:/srv/preview:ro" -v "$OUT/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
      nginx:1.27-alpine >/dev/null
  fi
  # fail loudly instead of serving an error page
  sleep 1
  for p in /preview/ /preview-panel/; do
    code=$(docker exec "$NAME" wget -q -S -O /dev/null "http://127.0.0.1$p" 2>&1 | awk '/HTTP\//{print $2}' | tail -1)
    [ "$code" = "200" ] || { echo "!! preview container answers $code for $p"; exit 1; }
  done
  echo "   container $NAME up"
}

routes() {
  # security headers mirror the live site's (user CSP for /preview/, panel CSP
  # for /preview-panel/), plus noindex so search engines skip the preview
  local common='add_header X-Content-Type-Options "nosniff" always; add_header Referrer-Policy "strict-origin-when-cross-origin" always; add_header X-Robots-Tag "noindex, nofollow" always; add_header Cross-Origin-Opener-Policy "same-origin" always;'
  local user_csp="default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'self' https://telegram.org https://*.telegram.org; base-uri 'self'; form-action 'self'; object-src 'none'"
  local panel_csp="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
  local tmp; tmp=$(mktemp)
  cat > "$tmp" <<INC
# preview of an unreleased frontend build — managed by scripts/preview.sh
location = /preview       { return 301 /preview/; }
location = /preview-panel { return 301 /preview-panel/; }
location ^~ /preview/ {
    set \$preview_up "http://$NAME:80";
    proxy_pass \$preview_up;
    proxy_set_header Host \$host;
    $common
    add_header Content-Security-Policy "$user_csp" always;
}
location ^~ /preview-panel/ {
    set \$preview_up "http://$NAME:80";
    proxy_pass \$preview_up;
    proxy_set_header Host \$host;
    $common
    add_header Content-Security-Policy "$panel_csp" always;
}
INC
  local ng; ng=$("${LIVE_COMPOSE[@]}" ps -q nginx)
  docker cp "$tmp" "$ng:$INC"; rm -f "$tmp"
  # add ONE include line to the TLS vhost (edited on the host with python —
  # the container's busybox sed is too limited to trust with the live config)
  docker cp "$ng:$SSL" "$OUT/10-ssl.conf.orig"
  python3 - "$OUT/10-ssl.conf.orig" "$OUT/10-ssl.conf.new" "$INC" <<'PY'
import sys
src, dst, inc = sys.argv[1:4]
s = open(src).read()
line = f"    include {inc};\n"
if line not in s:
    anchor = "location /.well-known/acme-challenge/"
    i = s.index(anchor); j = s.index("\n", i) + 1
    s = s[:j] + line + s[j:]
open(dst, "w").write(s)
PY
  docker cp "$OUT/10-ssl.conf.new" "$ng:$SSL"
  if "${LIVE_COMPOSE[@]}" exec -T nginx nginx -t >/dev/null 2>&1; then
    "${LIVE_COMPOSE[@]}" exec -T nginx nginx -s reload
    echo "   nginx routes /preview/ + /preview-panel/ active"
  else
    docker cp "$OUT/10-ssl.conf.orig" "$ng:$SSL"
    "${LIVE_COMPOSE[@]}" exec -T nginx rm -f "$INC"
    echo "!! nginx rejected the preview routes — original config restored, nothing reloaded"; exit 1
  fi
}

status() {
  docker ps --filter "name=^/$NAME$" --format '   container: {{.Names}} {{.Status}}' | grep . || echo "   container: not running"
  "${LIVE_COMPOSE[@]}" exec -T nginx sh -c "grep -q 'include $INC;' $SSL 2>/dev/null" && echo "   nginx routes: active" || echo "   nginx routes: not active"
  [ -d "$OUT/html" ] && echo "   build: $OUT/html ($(du -sh "$OUT/html" | cut -f1), $(stat -c %y "$OUT/html" | cut -c1-19))" || echo "   build: none"
}

remove() {
  local ng; ng=$("${LIVE_COMPOSE[@]}" ps -q nginx)
  if [ -n "$ng" ]; then
    mkdir -p "$OUT"; docker cp "$ng:$SSL" "$OUT/10-ssl.conf.cur" 2>/dev/null && {
      grep -v "include $INC;" "$OUT/10-ssl.conf.cur" > "$OUT/10-ssl.conf.clean"
      docker cp "$OUT/10-ssl.conf.clean" "$ng:$SSL"; }
    "${LIVE_COMPOSE[@]}" exec -T nginx rm -f "$INC" 2>/dev/null || true
  fi
  "${LIVE_COMPOSE[@]}" exec -T nginx nginx -t >/dev/null 2>&1 && "${LIVE_COMPOSE[@]}" exec -T nginx nginx -s reload >/dev/null 2>&1 || true
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  rm -rf "$OUT"
  rm -f "$ROOT"/frontend/*/src/theme/preview-palettes.json
  echo "==> preview removed (container, nginx routes, $OUT)"
}

case "${1:-}" in
  build)  build ;;
  up)     container; routes ;;
  update) build; container; routes ;;
  status) status ;;
  remove) remove ;;
  *) sed -n '2,19p' "$0"; exit 1 ;;
esac
