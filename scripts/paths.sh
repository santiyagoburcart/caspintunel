#!/usr/bin/env bash
# Admin-panel path and reseller-portal path (docs/paths.md). Runs on the HOST —
# the web container never gets docker access; it only writes a request file.
#
#   ./scripts/paths.sh show                    current paths, pending request, last result
#   ./scripts/paths.sh reset                   back to /panel + /agency
#   ./scripts/paths.sh set-admin /x            change the admin path   (recovery: works without the panel)
#   ./scripts/paths.sh set-portal /y           change the portal path
#   ./scripts/paths.sh apply-request           apply backups/.paths-request.json (cron, every minute)
#   ./scripts/paths.sh ensure                  write the default config if none exists (update.sh / install)
#
# Every change: render (validated) → nginx -t → reload → verify through nginx →
# on any failure the previous config is restored and reloaded.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
COMPOSE="${PATHS_COMPOSE:-docker compose -f docker-compose.yml -f docker-compose.prod.yml}"
DIR="$ROOT/nginx/paths"; ACTIVE="$DIR/active.conf"; JSON="$DIR/paths.json"
REQ="$ROOT/backups/.paths-request.json"; STATUS="$ROOT/backups/.paths-status.json"
TEMPLATE="$ROOT/nginx/paths.conf.template"; RENDER="$ROOT/nginx/render-paths.sh"
DEF_ADMIN=/panel; DEF_PORTAL=/agency

say() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
jget() { python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],''))" "$1" "$2" 2>/dev/null || true; }
current_admin() { local v; v=$([ -f "$JSON" ] && jget "$JSON" admin); echo "${v:-$DEF_ADMIN}"; }
current_portal() { local v; v=$([ -f "$JSON" ] && jget "$JSON" portal); echo "${v:-$DEF_PORTAL}"; }

write_status() {  # ok admin portal message
  mkdir -p "$(dirname "$STATUS")"
  python3 - "$STATUS" "$@" <<'PY'
import json, sys, time
path, ok, admin, portal, msg = sys.argv[1:6]
json.dump({"ok": ok == "1", "admin": admin, "portal": portal, "message": msg,
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, open(path, "w"))
PY
}

nginx_ok() { $COMPOSE exec -T nginx nginx -t >/dev/null 2>&1; }
nginx_reload() { $COMPOSE exec -T nginx nginx -s reload >/dev/null 2>&1; }
fetch() {  # fetch PATH → body (through nginx itself, as https so Django never redirects)
  $COMPOSE exec -T nginx wget -q -O - --header 'X-Forwarded-Proto: https' "http://127.0.0.1$1" 2>/dev/null
}
code() { $COMPOSE exec -T nginx sh -c "wget -S -q -O /dev/null 'http://127.0.0.1$1' 2>&1 | grep -m1 -o 'HTTP/1.1 [0-9]*' | cut -d' ' -f2" 2>/dev/null; }

verify() {  # admin portal
  local a="$1" p="$2" body
  sleep 1
  body="$(fetch "$a/" || true)"
  printf '%s' "$body" | grep -q "<base href=\"$a/\">" || { echo "admin page does not answer on $a/"; return 1; }
  body="$(fetch "/" || true)"
  printf '%s' "$body" | grep -q "name=\"ct-portal-path\" content=\"$p\"" || { echo "user site does not announce portal $p"; return 1; }
  if [ "$a" != "/panel" ] && [ "$(code /panel/)" != 404 ]; then echo "/panel/ still answers"; return 1; fi
  return 0
}

apply() {  # admin portal source
  local a="$1" p="$2" src="$3" tmp why
  mkdir -p "$DIR"
  tmp="$(mktemp "$DIR/.render.XXXXXX")"
  if ! sh "$RENDER" "$TEMPLATE" "$a" "$p" > "$tmp" 2> "$tmp.err"; then
    why="$(cat "$tmp.err")"; rm -f "$tmp" "$tmp.err"
    write_status 0 "$(current_admin)" "$(current_portal)" "rejected ($src): $why"
    die "$why"
  fi
  rm -f "$tmp.err"
  [ -f "$ACTIVE" ] && cp -p "$ACTIVE" "$ACTIVE.bak"
  [ -f "$JSON" ] && cp -p "$JSON" "$JSON.bak"
  mv "$tmp" "$ACTIVE"; chmod 644 "$ACTIVE"
  if nginx_ok && nginx_reload && why="$(verify "$a" "$p")"; then
    printf '{"admin": "%s", "portal": "%s"}\n' "$a" "$p" > "$JSON"
    rm -f "$ACTIVE.bak" "$JSON.bak"
    write_status 1 "$a" "$p" "applied ($src)"
    say "admin path: $a/   portal path: $p/"
    return 0
  fi
  why="${why:-nginx rejected the new config}"
  say "FAILED: $why — restoring the previous paths"
  if [ -f "$ACTIVE.bak" ]; then mv "$ACTIVE.bak" "$ACTIVE"; else sh "$RENDER" "$TEMPLATE" "$DEF_ADMIN" "$DEF_PORTAL" > "$ACTIVE"; fi
  [ -f "$JSON.bak" ] && mv "$JSON.bak" "$JSON"
  nginx_ok && nginx_reload || true
  write_status 0 "$(current_admin)" "$(current_portal)" "rolled back ($src): $why"
  exit 1
}

exec 9>"$ROOT/backups/.paths.lock" 2>/dev/null || exec 9>/tmp/caspintunel-paths.lock
flock -n 9 || { echo "another paths change is running"; exit 0; }

case "${1:-show}" in
  show)
    echo "admin path : $(current_admin)/"
    echo "portal path: $(current_portal)/"
    [ -f "$REQ" ] && echo "pending    : $(cat "$REQ")"
    [ -f "$STATUS" ] && echo "last result: $(cat "$STATUS")"
    true ;;
  ensure)
    if [ ! -s "$ACTIVE" ]; then
      mkdir -p "$DIR"; sh "$RENDER" "$TEMPLATE" "$DEF_ADMIN" "$DEF_PORTAL" > "$ACTIVE"; say "default paths written"
    else
      # keep the generated file in step with a newer template (same paths)
      tmp="$(mktemp "$DIR/.render.XXXXXX")"
      sh "$RENDER" "$TEMPLATE" "$(current_admin)" "$(current_portal)" > "$tmp" && mv "$tmp" "$ACTIVE" || rm -f "$tmp"
    fi ;;
  reset) apply "$DEF_ADMIN" "$DEF_PORTAL" "reset (cli)" ;;
  set-admin) apply "${2:?usage: set-admin /path}" "$(current_portal)" "set-admin (cli)" ;;
  set-portal) apply "$(current_admin)" "${2:?usage: set-portal /path}" "set-portal (cli)" ;;
  apply-request)
    [ -f "$REQ" ] || exit 0
    a="$(jget "$REQ" admin)"; p="$(jget "$REQ" portal)"; by="$(jget "$REQ" requested_by)"
    rm -f "$REQ"                                   # one attempt per request, never a loop
    apply "${a:-$(current_admin)}" "${p:-$(current_portal)}" "panel request by ${by:-?}" ;;
  *) sed -n '2,13p' "$0"; exit 2 ;;
esac
