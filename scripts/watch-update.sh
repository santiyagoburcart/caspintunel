#!/usr/bin/env bash
# Host-side watcher for the panel "Update" button.
# Run under systemd or cron on the server:
#   */2 * * * *  /opt/caspintunel/scripts/watch-update.sh --prod >> /var/log/caspintunel-update.log 2>&1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SENTINEL="$ROOT/backups/.update-requested"   # bind-mounted into the web container

[ -f "$SENTINEL" ] || exit 0

echo "[$(date -Is)] update requested:"
cat "$SENTINEL" || true
rm -f "$SENTINEL"

"$ROOT/update.sh" "${1:---prod}"
echo "[$(date -Is)] update finished"
