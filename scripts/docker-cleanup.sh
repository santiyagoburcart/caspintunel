#!/usr/bin/env bash
# Remove Docker leftovers of old releases (run by update.sh after a deploy).
# Keeps: every image a container uses, our :latest + :rollback tags (= the
# previous release for ./update.sh --rollback), build cache used in the last
# 72 h (the next build stays incremental). Other projects' images are untouched.
set -uo pipefail

REPOS="caspintunel-backend caspintunel-frontend-user caspintunel-frontend-admin caspintunel-nginx"

echo "==> docker cleanup"
# 1) our own images under any tag other than latest/rollback (older releases)
for repo in $REPOS; do
  docker images "$repo" --format '{{.Tag}}' | grep -vxE 'latest|rollback|<none>' | while read -r tag; do
    docker rmi "$repo:$tag" >/dev/null 2>&1 && echo "   removed $repo:$tag"
  done
done
# 1b) leftovers of the throw-away test stacks (test-paths.sh / test-domain.sh)
docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^(pathtest|domaintest)-' | while read -r img; do
  docker rmi "$img" >/dev/null 2>&1 && echo "   removed $img"
done
# 2) untagged images (a :rollback/:latest tag that moved on leaves these behind)
docker image prune -f 2>/dev/null | tail -1 | sed 's/^/   images: /'
# 3) build cache not used for 24 h (it reached 6 GB with 72 h)
docker builder prune -f --filter until=24h 2>/dev/null | tail -1 | sed 's/^/   build cache: /'
docker system df 2>/dev/null | sed 's/^/   /'
exit 0
