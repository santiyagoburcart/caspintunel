#!/usr/bin/env bash
# One-shot UI checks on the ISOLATED ui-audit stack (fake data; never the live
# DB / Redis / API). Builds this checkout's SPAs, starts the stack, runs the
# requested checks in the pinned Playwright image on the stack's own network,
# then tears the stack down.
#
#   scripts/ui-audit/run.sh [audit] [density] [suites] [contrast]   (default: all)
#   OUT=/path   results + screenshots (default: $TMPDIR/ui-audit-<ts>)
#   KEEP=1      leave the stack running afterwards (then: stack.sh down)
#   PATHS=regex audit only the matching pages, e.g. PATHS='^/panel/apps$'
#   PATHS=regex audit only matching pages, e.g. PATHS='^/panel/apps$'
#
# Offline alternative for the logged-out pages only (no stack):
#   API= node scripts/ui-audit/audit.mjs   (see the header of audit.mjs)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
WHAT=("${@:-audit density suites contrast}"); WHAT=(${WHAT[*]})
OUT="${OUT:-${TMPDIR:-/tmp}/ui-audit-$(date +%Y%m%d-%H%M%S)}"
PW_IMAGE=mcr.microsoft.com/playwright:v1.49.1-noble
mkdir -p "$OUT/pw" "$OUT/dist"

echo "==> build SPAs"
for app in user admin; do
  ( cd "frontend/$app"
    [ -d node_modules ] || npm ci --no-audit --no-fund --loglevel=error
    npx vite build --logLevel error --outDir "$OUT/dist/$app" --emptyOutDir )
done

echo "==> playwright (npm package matching the image)"
[ -d "$OUT/pw/node_modules/playwright" ] || docker run --rm -v "$OUT/pw:/pw" -w /pw "$PW_IMAGE" \
  sh -c 'echo "{\"private\":true}" > package.json && npm i --no-audit --no-fund --loglevel=error playwright@1.49.1' >/dev/null

cleanup() { [ "${KEEP:-0}" = 1 ] || scripts/ui-audit/stack.sh down >/dev/null 2>&1 || true; }
trap cleanup EXIT
echo "==> isolated stack + fake data"
scripts/ui-audit/stack.sh up
NET="$(scripts/ui-audit/stack.sh net)"

# pw [-e K=V]... cmd args...   (env flags first, then the command run inside the image)
pw() {
  local envs=()
  while [ "${1:-}" = "-e" ]; do envs+=("$1" "$2"); shift 2; done
  docker run --rm --network "$NET" --ipc=host -e API=http://web:8000 -e PW_REQUIRE=/o/pw/x.js \
    -e USER_DIST=/o/dist/user -e ADMIN_DIST=/o/dist/admin "${envs[@]}" -v "$ROOT:/w:ro" -v "$OUT:/o" "$PW_IMAGE" "$@"
}
rc=0
for w in "${WHAT[@]}"; do
  case "$w" in
    contrast) node scripts/ui-audit/glass-contrast.mjs | tail -1 || rc=1 ;;
    density)  pw -e MODE=density -e SHOTS=1 -e OUT=/o/density node /w/scripts/ui-audit/audit.mjs || rc=1 ;;
    audit)    pw -e MODE=audit -e SHOTS=1 -e "PATHS=${PATHS:-}" -e OUT=/o/audit node /w/scripts/ui-audit/audit.mjs | tail -40 || rc=1 ;;
    suites)   pw -e OUT=/o/suites node /w/scripts/ui-audit/run-suites.mjs || rc=1 ;;
    *) echo "unknown check: $w" >&2; rc=2 ;;
  esac
done
echo "results: $OUT"
exit $rc
