#!/usr/bin/env bash
# Daily disk check (host side; cron, installed by update.sh). Measures the biggest
# folders / Docker volumes / MySQL binlogs and writes backups/.disk-report.json,
# which the app reads (apps/ops/disk.py → Monitoring page + Telegram alerts).
# The previous report is kept as .disk-report.prev.json for day-over-day growth.
# Also trims Docker build cache older than 24 h (the next build stays incremental).
#   ./scripts/disk-report.sh            measure + trim + write the report
#   ./scripts/disk-report.sh --dry-run  print the JSON only
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/backups/.disk-report.json"
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1

bytes() { du -sxb "$1" 2>/dev/null | cut -f1; }
items=""
add() {   # add <label> <path>
  local b; b=$(bytes "$2"); [ -n "$b" ] || return 0
  items="$items{\"label\":\"$1\",\"path\":\"$2\",\"bytes\":$b},"
}

if [ $DRY -eq 0 ]; then
  docker builder prune -f --filter until=24h >/dev/null 2>&1 || true
fi

# top-level folders of the root filesystem
for d in /var/lib/containerd /var/lib/docker/containers /var/log /root /tmp /home /opt /usr; do
  [ -e "$d" ] && add "$d" "$d"
done
# every Docker volume (database, media, redis, …) — anonymous ones included
for v in $(docker volume ls -q 2>/dev/null); do
  p="/var/lib/docker/volumes/$v/_data"
  [ -d "$p" ] && add "volume:$v" "$p"
done
add "backups" "$ROOT/backups"
# MySQL binary logs inside the database volume
DBV="/var/lib/docker/volumes/caspintunel_db_data/_data"
if [ -d "$DBV" ]; then
  bl=$(find "$DBV" -maxdepth 1 -name 'binlog.[0-9]*' -printf '%s\n' 2>/dev/null | awk '{s+=$1} END{print s+0}')
  items="$items{\"label\":\"mysql-binlogs\",\"path\":\"$DBV/binlog.*\",\"bytes\":$bl},"
fi

read -r total used avail < <(df -B1 --output=size,used,avail / | tail -1)
pct=$(awk -v u="$used" -v a="$avail" 'BEGIN{printf "%.1f", (u+a) ? u*100/(u+a) : 0}')  # same as df / psutil
img=$(docker system df --format '{{.Type}}: {{.Size}} (reclaimable {{.Reclaimable}})' 2>/dev/null | tr '\n' ';' | tr -d '\t' | sed 's/"/\\"/g')

json="{\"generated_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"disk\":{\"total\":$total,\"used\":$used,\"free\":$avail,\"percent\":$pct},\"items\":[${items%,}],\"docker\":\"$img\"}"

if [ $DRY -eq 1 ]; then echo "$json"; exit 0; fi
mkdir -p "$ROOT/backups"
[ -f "$OUT" ] && cp -f "$OUT" "$ROOT/backups/.disk-report.prev.json"
printf '%s\n' "$json" > "$OUT.tmp" && mv -f "$OUT.tmp" "$OUT"
echo "disk report: ${pct}% used, written to $OUT"
