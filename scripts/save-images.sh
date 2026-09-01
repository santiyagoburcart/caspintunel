#!/usr/bin/env bash
# Run on an ONLINE machine (same CPU arch as the target). Builds every image and
# bundles all images into one tarball for an air-gapped server.
#
#   ./scripts/save-images.sh                 -> dist/caspintunel-images-<version>.tar.gz
#   ./scripts/save-images.sh /mnt/usb        -> writes the tarball there
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"

OUT_DIR="${1:-dist}"
VERSION="$(cat VERSION)"
mkdir -p "$OUT_DIR"
TARBALL="$OUT_DIR/caspintunel-images-${VERSION}.tar.gz"

CF="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

echo "==> building application images"
$CF build

echo "==> pulling base/runtime images"
$CF pull db redis phpmyadmin certbot mailserver 2>/dev/null || true

# resolve the exact image refs compose will use
IMAGES=$($CF config --images | sort -u)
echo "==> images to bundle:"; echo "$IMAGES" | sed 's/^/    /'

echo "==> docker save -> $TARBALL  (this is large, be patient)"
# shellcheck disable=SC2086
docker save $IMAGES | gzip > "$TARBALL"

{
  echo "caspintunel offline image bundle"
  echo "version: $VERSION"
  echo "created: $(date -Is)"
  echo "arch:    $(docker version -f '{{.Server.Arch}}')"
  echo "images:"; echo "$IMAGES" | sed 's/^/  - /'
} > "$OUT_DIR/caspintunel-images-${VERSION}.txt"

echo
echo "done: $TARBALL  ($(du -h "$TARBALL" | cut -f1))"
echo "copy it + this whole repo to the target, then: ./scripts/load-images.sh $TARBALL"
