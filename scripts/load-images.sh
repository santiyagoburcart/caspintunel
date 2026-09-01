#!/usr/bin/env bash
# Run on the AIR-GAPPED server. Loads the image bundle produced by save-images.sh.
#
#   ./scripts/load-images.sh caspintunel-images-1.0.0.tar.gz
set -euo pipefail

TARBALL="${1:-}"
[ -n "$TARBALL" ] || { echo "usage: $0 <caspintunel-images-*.tar.gz>"; exit 1; }
[ -s "$TARBALL" ] || { echo "!! $TARBALL not found"; exit 1; }

echo "==> docker load < $TARBALL"
gunzip -c "$TARBALL" | docker load

echo
echo "loaded images:"
docker images --format '  {{.Repository}}:{{.Tag}}  {{.Size}}' | grep -E 'caspintunel|mysql|redis|phpmyadmin|certbot|docker-mailserver' || true
echo
echo "next: ./install.sh   (choose Install, offline mode)"
