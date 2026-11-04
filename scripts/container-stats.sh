#!/usr/bin/env bash
# v1.39.0 container memory watch (host side; cron every 5 min, installed by update.sh). Read-only: docker stats /
# inspect, /proc/meminfo, /proc/pressure/memory, /proc/loadavg. Writes backups/.container-stats.json, which the app
# reads (apps/ops/containers.py → Monitoring card + Telegram alerts). The app never gets the Docker socket.
#   ./scripts/container-stats.sh            sample + write
#   ./scripts/container-stats.sh --dry-run  print the JSON only
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/backups/.container-stats.json"
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1

to_bytes() {   # "205.1MiB" / "3.73GiB" / "512kB" → bytes
  awk -v v="$1" 'BEGIN{
    n=v+0; u=v; gsub(/[0-9.]/,"",u)
    m["B"]=1; m["kB"]=1000; m["KB"]=1000; m["KiB"]=1024; m["MB"]=1000^2; m["MiB"]=1024^2; m["GB"]=1000^3; m["GiB"]=1024^3
    printf "%.0f", n*((u in m)?m[u]:1) }'
}

items=""
while IFS='|' read -r name cpu mem; do
  [ -n "$name" ] || continue
  used=$(to_bytes "${mem%% / *}")
  # the real limit (0 = none) and health facts come from inspect, not from the "/ total" of docker stats
  read -r limit oom restarts state started < <(docker inspect -f '{{.HostConfig.Memory}} {{.State.OOMKilled}} {{.RestartCount}} {{.State.Status}} {{.State.StartedAt}}' "$name" 2>/dev/null || echo "0 false 0 unknown -")
  proj=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$name" 2>/dev/null)
  svc=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$name" 2>/dev/null)
  items="$items{\"name\":\"$name\",\"project\":\"$proj\",\"service\":\"$svc\",\"cpu\":\"${cpu%\%}\",\"mem_used\":$used,\"mem_limit\":${limit:-0},\"oom_killed\":${oom:-false},\"restarts\":${restarts:-0},\"state\":\"$state\",\"started_at\":\"$started\"},"
done < <(docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}' 2>/dev/null)

mt=$(awk '/^MemTotal:/{print $2*1024}' /proc/meminfo); ma=$(awk '/^MemAvailable:/{print $2*1024}' /proc/meminfo)
st=$(awk '/^SwapTotal:/{print $2*1024}' /proc/meminfo); sf=$(awk '/^SwapFree:/{print $2*1024}' /proc/meminfo)
psi_some=$(awk '/^some/{split($3,a,"="); print a[2]}' /proc/pressure/memory 2>/dev/null); psi_full=$(awk '/^full/{split($3,a,"="); print a[2]}' /proc/pressure/memory 2>/dev/null)
read -r l1 l5 l15 _ < /proc/loadavg
cpus=$(nproc)

json="{\"generated_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"host\":{\"cpus\":$cpus,\"load1\":$l1,\"load5\":$l5,\"load15\":$l15,\"mem_total\":$mt,\"mem_available\":$ma,\"swap_total\":$st,\"swap_used\":$((st - sf)),\"psi_some_avg60\":${psi_some:-0},\"psi_full_avg60\":${psi_full:-0}},\"containers\":[${items%,}]}"

if [ $DRY -eq 1 ]; then echo "$json"; exit 0; fi
mkdir -p "$ROOT/backups"
printf '%s\n' "$json" > "$OUT.tmp" && mv -f "$OUT.tmp" "$OUT"
