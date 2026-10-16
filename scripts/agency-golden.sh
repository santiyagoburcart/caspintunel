#!/usr/bin/env bash
# Produce the GOLDEN expectations by running the ORIGINAL PAMP v1.5.3 code.
#
#   ./scripts/agency-golden.sh synthetic             → backend/apps/agency/golden/expected_pamp_v153.json (committed)
#   ./scripts/agency-golden.sh real DUMP RESPONSES   → backend/.golden_local/real/expected.json (local only, real data)
#
# PAMP is cloned read-only at tag v1.5.3 and built with its own Dockerfile
# (image pamp-golden:1.5.3). It runs on an isolated network against a
# throw-away MySQL; the panel is mocked (`responses`), so nothing leaves the
# host. The agency side is compared by tests/test_golden.py (./scripts/test.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:?synthetic | real DUMP RESPONSES}"
PAMP_SRC="${PAMP_SRC:-/root/pamp-v153}"
TAG=v1.5.3
NET="agency-golden-$$"
DB="agency-golden-db-$$"
GOLDEN="$ROOT/backend/apps/agency/golden"

if [ ! -d "$PAMP_SRC/.git" ]; then
  git clone -q --depth 1 --branch "$TAG" https://github.com/santiyagoburcart/PAMP.git "$PAMP_SRC"
  chmod -R a-w "$PAMP_SRC"
fi
[ "$(git -C "$PAMP_SRC" describe --tags --exact-match 2>/dev/null)" = "$TAG" ] || { echo "PAMP source is not at $TAG"; exit 1; }

if ! docker image inspect pamp-golden:1.5.3 >/dev/null 2>&1; then
  docker build -q -t pamp-golden:base "$PAMP_SRC" >/dev/null
  printf 'FROM pamp-golden:base\nRUN pip install --no-cache-dir responses==0.25.6\n' | docker build -q -t pamp-golden:1.5.3 - >/dev/null
fi

cleanup() { docker rm -f "$DB" >/dev/null 2>&1 || true; docker network rm "$NET" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker network create --internal "$NET" >/dev/null
PW="golden-$(head -c 12 /dev/urandom | base64 | tr -dc A-Za-z0-9)"
docker run -d --name "$DB" --network "$NET" -e MYSQL_ROOT_PASSWORD="$PW" -e MYSQL_DATABASE=pamp \
  -e MYSQL_USER=pamp -e MYSQL_PASSWORD="$PW" mysql:8.0 --character-set-server=utf8mb4 >/dev/null
for i in $(seq 1 60); do docker exec "$DB" mysqladmin ping -uroot -p"$PW" --silent >/dev/null 2>&1 && break; sleep 2; done
sleep 5

ENVS=(-e SECRET_KEY="golden-$(head -c 24 /dev/urandom | base64 | tr -dc A-Za-z0-9)" -e DB_NAME=pamp -e DB_USER=pamp
      -e DB_PASSWORD="$PW" -e DB_HOST="$DB" -e DB_PORT=3306 -e CELERY_BROKER_URL=memory://
      -e CELERY_RESULT_BACKEND=cache+memory:// -e ALLOWED_HOSTS='*')
run_pamp() {
  docker run --rm --network "$NET" "${ENVS[@]}" --entrypoint python \
    -v "$PAMP_SRC:/pamp:ro" -v "$GOLDEN:/golden:ro" -v "$OUT_DIR:/out" -w /pamp pamp-golden:1.5.3 /golden/run_pamp.py "$@"
}

case "$MODE" in
  synthetic)
    OUT_DIR="$(mktemp -d)"
    run_pamp /golden/scenario.json /out/expected.json
    cp "$OUT_DIR/expected.json" "$GOLDEN/expected_pamp_v153.json"
    echo "wrote backend/apps/agency/golden/expected_pamp_v153.json"
    ;;
  real)
    DUMP="${2:?dump file}"; RESP="${3:?recorded responses json}"
    OUT_DIR="$ROOT/backend/.golden_local/real"; mkdir -p "$OUT_DIR"; chmod 700 "$OUT_DIR"
    cp "$RESP" "$OUT_DIR/responses.json"; cp "$DUMP" "$OUT_DIR/pamp.sql.gz"; chmod 600 "$OUT_DIR"/*
    gunzip -c "$DUMP" | docker exec -i "$DB" sh -c "mysql -uroot -p'$PW' pamp" 2>/dev/null
    run_pamp --from-db /out/responses.json /out/expected.json
    chmod 600 "$OUT_DIR/expected.json"
    echo "wrote backend/.golden_local/real/expected.json (local only)"
    ;;
  *) echo "unknown mode $MODE"; exit 2 ;;
esac
