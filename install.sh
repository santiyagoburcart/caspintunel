#!/usr/bin/env bash
# One-click installer for caspintunel.
#   ./install.sh              interactive dev setup
#   ./install.sh --prod       production (gunicorn, static SPAs, TLS-ready)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PROD=0
[ "${1:-}" = "--prod" ] && PROD=1
COMPOSE="docker compose -f docker-compose.yml"
[ "$PROD" = 1 ] && COMPOSE="$COMPOSE -f docker-compose.prod.yml"

py()      { $COMPOSE exec -T web python manage.py "$@"; }
gen_key() { python3 -c "import secrets;print(secrets.token_urlsafe(64))"; }
gen_fer() { python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())" 2>/dev/null \
            || docker run --rm python:3.12-slim sh -c "pip -q install cryptography && python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())'"; }

# ---------------------------------------------------------------- .env
if [ ! -f .env ]; then
  echo "==> creating .env"
  cp .env.example .env
  read -rp "Server public IP: " SERVER_IP
  read -rp "Domain [aicaspin.ir]: " DOMAIN; DOMAIN=${DOMAIN:-aicaspin.ir}
  read -rp "DB password: " DB_PASSWORD
  read -rp "DB root password: " DB_ROOT_PASSWORD
  read -rp "Panel base URL [https://pas.hunaex.shop]: " PANEL_URL; PANEL_URL=${PANEL_URL:-https://pas.hunaex.shop}
  read -rp "Panel admin username: " PANEL_USER
  read -rsp "Panel admin password: " PANEL_PASS; echo
  read -rp "Admin username: " SU_NAME
  read -rsp "Admin password: " SU_PASS; echo
  read -rp "Admin email: " SU_EMAIL
  read -rp "Cloudflare API token (blank to skip DNS): " CF_TOKEN || true
  read -rp "GitHub token (blank to skip repo push): " GH_TOKEN || true

  python3 - "$PWD/.env" <<PY
import sys, re
vals = {
  "SERVER_IP": "$SERVER_IP", "DOMAIN": "$DOMAIN",
  "ALLOWED_HOSTS": "$DOMAIN,www.$DOMAIN,$SERVER_IP,localhost,127.0.0.1",
  "CORS_ALLOWED_ORIGINS": "https://$DOMAIN,https://www.$DOMAIN",
  "PUBLIC_BASE_URL": "https://$DOMAIN",
  "SECRET_KEY": "$(gen_key)", "FIELD_ENCRYPTION_KEY": "$(gen_fer)",
  "DB_PASSWORD": "$DB_PASSWORD", "DB_ROOT_PASSWORD": "$DB_ROOT_PASSWORD",
  "PANEL_BASE_URL": "$PANEL_URL",
  "PANEL_ADMIN_USERNAME": "$PANEL_USER", "PANEL_ADMIN_PASSWORD": "$PANEL_PASS",
  "DJANGO_SUPERUSER_USERNAME": "$SU_NAME", "DJANGO_SUPERUSER_PASSWORD": "$SU_PASS",
  "DJANGO_SUPERUSER_EMAIL": "$SU_EMAIL",
  "CLOUDFLARE_API_TOKEN": "${CF_TOKEN:-}", "GITHUB_TOKEN": "${GH_TOKEN:-}",
}
p = sys.argv[1]
out = []
for ln in open(p).read().splitlines():
    m = re.match(r"^([A-Z_]+)=", ln)
    out.append(f"{m.group(1)}={vals[m.group(1)]}" if m and m.group(1) in vals else ln)
open(p, "w").write("\n".join(out) + "\n")
PY
  chmod 600 .env
  echo "==> .env written (chmod 600, git-ignored)"
else
  echo "==> .env exists — keeping it"
fi

# ---------------------------------------------------------------- stack
echo "==> build"; $COMPOSE build
echo "==> up";    $COMPOSE up -d --remove-orphans
echo "==> waiting for the database"; sleep 8
py migrate --noinput
py seed
set +e; py createsuperuser --noinput; set -e

# ---------------------------------------------------------------- DNS (optional)
if grep -q '^CLOUDFLARE_API_TOKEN=.\+' .env; then
  echo
  read -rp "Configure Cloudflare DNS now (A/www/mail/MX/SPF/DKIM/DMARC)? [y/N] " a
  if [ "${a:-N}" = "y" ]; then
    py configure_dns --apply
  else
    echo "   later: $COMPOSE exec web python manage.py configure_dns --apply"
  fi
fi

# ---------------------------------------------------------------- GitHub (optional)
if grep -q '^GITHUB_TOKEN=.\+' .env && [ ! -d .git ]; then
  echo
  read -rp "Create the private GitHub repo and push now? [y/N] " g
  [ "${g:-N}" = "y" ] && ./scripts/setup_github.sh
fi

echo
echo "Done — version $(cat VERSION)"
echo "  site   : http://$([ "$PROD" = 1 ] && echo "$DOMAIN" || echo localhost)/"
echo "  panel  : .../panel/"
echo "  api    : .../api/v1/   docs: .../api/docs/"
[ "$PROD" = 1 ] && echo "  TLS    : issue certs (e.g. certbot) into nginx/certs/ then reload nginx"
