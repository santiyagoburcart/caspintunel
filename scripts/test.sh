#!/usr/bin/env bash
# Run the backend test suite in the ISOLATED test stack (docker-compose.test.yml):
# its own MySQL + Redis on tmpfs, its own network — never the live services.
#   ./scripts/test.sh                       whole suite
#   ./scripts/test.sh apps/accounts -k phone   any pytest args
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# explicit -f / -p: ignores COMPOSE_FILE from .env (that one means PROD)
TC=(docker compose -p caspintunel-test -f docker-compose.test.yml)

# throw-away keys for this run only (nothing from the live .env is used)
export TEST_SECRET_KEY="test-$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9')"
export TEST_FIELD_ENCRYPTION_KEY="$(head -c 32 /dev/urandom | base64 | tr '+/' '-_')"

cleanup() { "${TC[@]}" down --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

if [ $# -gt 0 ]; then
  "${TC[@]}" run --rm tests python -m pytest -p no:warnings "$@"
else
  "${TC[@]}" run --rm tests
fi
