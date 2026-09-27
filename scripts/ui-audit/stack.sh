#!/usr/bin/env bash
# Isolated UI-audit stack: test DB + Redis (tmpfs) + API server + FAKE data.
#   scripts/ui-audit/stack.sh up      start, migrate, seed, load fake data
#   scripts/ui-audit/stack.sh down    tear everything down (data is on tmpfs)
#   scripts/ui-audit/stack.sh net     print the docker network name
# The API runs with config.settings.test, whose guard refuses any DB/Redis host
# other than test-db / test-redis. Nothing from the live .env is used.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
P=caspintunel-uiaudit
TC=(docker compose -p "$P" -f docker-compose.test.yml -f scripts/ui-audit/docker-compose.uiaudit.yml)

case "${1:-}" in
  up)
    export TEST_SECRET_KEY="uiaudit-$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9')"
    export TEST_FIELD_ENCRYPTION_KEY="$(head -c 32 /dev/urandom | base64 | tr '+/' '-_')"
    "${TC[@]}" up -d test-db test-redis
    "${TC[@]}" run --rm --no-deps -T web python manage.py migrate --noinput >/dev/null
    "${TC[@]}" run --rm --no-deps -T web python manage.py seed >/dev/null
    "${TC[@]}" up -d web
    "${TC[@]}" exec -T web sh -c 'python manage.py shell < /ui-audit/seed_fake.py'
    for _ in $(seq 60); do
      "${TC[@]}" exec -T web python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/',timeout=2)" >/dev/null 2>&1 && break
      sleep 1
    done
    echo "ui-audit stack up on network ${P}_default (api: http://web:8000)"
    ;;
  down) TEST_SECRET_KEY=x TEST_FIELD_ENCRYPTION_KEY=x "${TC[@]}" down --remove-orphans -v ;;
  net) echo "${P}_default" ;;
  *) echo "usage: $0 up|down|net" >&2; exit 2 ;;
esac
