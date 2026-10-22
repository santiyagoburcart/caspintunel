#!/usr/bin/env bash
# Server migration — test the NEW server BEFORE switching DNS.  docs/migration.md
#
#   ./scripts/migrate-check.sh NEW_SERVER_IP [domain]        run from anywhere: laptop, old or new server
#   ./scripts/migrate-check.sh NEW_SERVER_IP domain --http   plain HTTP (no certificate on the new server yet)
#
# Every request goes to NEW_SERVER_IP but with the real host name (curl
# --resolve), exactly what a browser does once DNS is switched — DNS itself is
# not touched and nothing is written. Then follow the manual checklist it prints.
set -uo pipefail
IP="${1:-}"; DOMAIN="${2:-}"; SCHEME=https
[ "${3:-}" = "--http" ] && SCHEME=http
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -n "$DOMAIN" ] || DOMAIN="$(grep -m1 '^DOMAIN=' "$ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d "\"'")"
[ -n "$IP" ] && [ -n "$DOMAIN" ] || { sed -n '2,10p' "$0"; exit 2; }
PORT=$([ "$SCHEME" = https ] && echo 443 || echo 80)
BASE="$SCHEME://$DOMAIN"
C=(curl -sS --max-time 15 --resolve "$DOMAIN:$PORT:$IP")
FAIL=0
pass() { printf '  \033[1;32mPASS\033[0m  %s\n' "$*"; }
fail() { printf '  \033[1;31mFAIL\033[0m  %s\n' "$*"; FAIL=$((FAIL + 1)); }
code() { "${C[@]}" -o /dev/null -w '%{http_code}' "$@" 2>/dev/null; }
expect() {  # expect "label" "allowed codes" curl-args…
  local label="$1" want="$2" got; shift 2
  got="$(code "$@")"
  case " $want " in *" $got "*) pass "$label ($got)" ;; *) fail "$label — got $got, expected one of: $want" ;; esac
}

echo "Testing $BASE on $IP (DNS untouched)"
if [ "$SCHEME" = https ]; then
  if "${C[@]}" -o /dev/null "$BASE/" 2>/dev/null; then
    exp=$(echo | openssl s_client -connect "$IP:443" -servername "$DOMAIN" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
    pass "TLS certificate valid for $DOMAIN (expires ${exp:-?})"
  else
    fail "TLS: no valid certificate for $DOMAIN on $IP (try --http, or restore/issue the certificate)"
  fi
fi
expect "user site /"                    "200"         "$BASE/"
expect "admin panel /panel/"            "200"         "$BASE/panel/"
expect "API health"                     "200"         "$BASE/api/v1/health/"
expect "public config"                  "200"         "$BASE/api/v1/config/"
expect "plans"                          "200"         "$BASE/api/v1/plans/"
expect "customer API needs login"       "401"         "$BASE/api/v1/services/"
expect "admin API needs staff login"    "401 403"     "$BASE/api/v1/admin/payments/pending/"
expect "SMS device API reachable (rejects a request without a device token)" "401 403" \
       "$BASE/api/v1/payments/sms/ping/"
expect "receipts are not public"        "404"         "$BASE/media/receipts/"
expect "ticket files are not public"    "404"         "$BASE/media/tickets/"
# WebSocket: the upgrade must reach daphne (101, or 403 because no token was sent);
# a 502/504 means daphne is down
expect "WebSocket /ws/notifications/ reaches daphne" "101 403" \
       --http1.1 -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' \
       -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' -H "Origin: $BASE" --max-time 5 "$BASE/ws/notifications/"

cat <<CHECKLIST

Manual checklist — in a browser that sees the NEW server:
  add this line to the hosts file of YOUR computer, test, then REMOVE it again
      $IP  $DOMAIN
  (Linux/macOS: /etc/hosts — Windows: C:\\Windows\\System32\\drivers\\etc\\hosts;
   use a private window so nothing is cached)

  [ ] customer login -> dashboard shows the same services / usage as on the old server
  [ ] a service's QR opens (branded background); the subscription link is unchanged
  [ ] purchase history shows the old orders
  [ ] /panel/ staff login -> dashboard numbers equal the old server's
  [ ] payments queue lists the pending payments, a receipt image opens, the "online" dot is green (WebSocket)
  [ ] Panel connection -> "Test connection" is green (PasarGuard reachable from the NEW IP;
      if the panel has an IP allow-list, add $IP)
  [ ] Services -> open one -> live usage loads from the panel
  [ ] Settings -> Email -> "Send test email" arrives
  [ ] Settings -> SMS devices are listed; SMS log shows the old messages
  [ ] Branding, plans, bank cards, CMS pages, themes look the same
  on the new server:
  [ ] ./scripts/migrate-import.sh --status      -> MIGRATION_HOLD 1, web/daphne healthy
  [ ] docker compose exec web python manage.py panel_check
  DO NOT test a real payment or approve a real order before the final import:
  bots and celery are on hold (no service is delivered) and a later import replaces this copy.
CHECKLIST
if [ "$FAIL" = 0 ]; then echo; echo "All automatic checks passed."; exit 0; fi
echo; echo "$FAIL automatic check(s) failed."; exit 1
