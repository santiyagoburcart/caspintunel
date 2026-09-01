#!/usr/bin/env bash
# Create the private GitHub repo (if missing) and push. Reads GITHUB_TOKEN /
# GITHUB_REPO from .env. The token is used only for this run and never written
# into .git/config.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"

set -a; . ./.env; set +a
: "${GITHUB_TOKEN:?set GITHUB_TOKEN in .env}"
REPO="${GITHUB_REPO:-caspintunel}"

OWNER=$(curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user \
        | python3 -c "import sys,json;print(json.load(sys.stdin)['login'])")
echo "==> owner: $OWNER  repo: $REPO"

if curl -fsSL -o /dev/null -H "Authorization: Bearer $GITHUB_TOKEN" \
     "https://api.github.com/repos/$OWNER/$REPO"; then
  echo "==> repo already exists"
else
  echo "==> creating private repo"
  curl -fsSL -X POST -H "Authorization: Bearer $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" https://api.github.com/user/repos \
    -d "{\"name\":\"$REPO\",\"private\":true,\"description\":\"caspintunel — VPN sales system\",\"has_wiki\":false,\"has_projects\":false}" \
    >/dev/null
fi

[ -d .git ] || { git init -q; git branch -M main; }
git add -A
git -c user.email="deploy@${DOMAIN:-caspin.skin}" -c user.name="caspintunel deploy" \
    commit -q -m "Deploy $(cat VERSION)" || echo "   (nothing to commit)"

# push with an ephemeral credential; leave a clean remote behind
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$OWNER/$REPO.git"
git -c credential.helper= \
    -c "http.https://github.com/.extraheader=Authorization: Bearer $GITHUB_TOKEN" \
    push -u origin main

echo "==> pushed to https://github.com/$OWNER/$REPO (private)"
