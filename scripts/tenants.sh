#!/usr/bin/env bash
# Store domains + TLS on the HOST (docs/multi-tenant.md §7). The web container never gets docker access; it only writes
# backups/.tenant-domains.json, this reconciles nginx + certificates with it (scripts/tenants_host.py).
#
#   ./scripts/tenants.sh show            wanted hosts, last result per host, generated nginx files
#   ./scripts/tenants.sh apply-request   reconcile (cron, every minute): pre-check → HTTP-01 certificate → nginx file →
#                                        nginx -t → reload → TLS verify → rollback on failure
#
# Recovery without the panel: delete nginx/tenants/<host>.conf and reload nginx
# (docker compose exec nginx nginx -s reload). Our own domain (scripts/domain.sh) is never touched.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec 9>"$ROOT/backups/.tenants.lock" 2>/dev/null || exec 9>/tmp/caspintunel-tenants.lock
flock -n 9 || { echo "another store-domain run is in progress"; exit 0; }
exec python3 "$ROOT/scripts/tenants_host.py" "${1:-show}"
