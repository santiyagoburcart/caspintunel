#!/usr/bin/env bash
# Issue the first Let's Encrypt cert for the domain, then enable HTTPS.
#
#   ./scripts/init-letsencrypt.sh                 # uses DOMAIN + admin email from .env
#   ./scripts/init-letsencrypt.sh --staging       # LE staging (no rate limits, untrusted cert)
#   ./scripts/init-letsencrypt.sh --prod ...      # pass through to production compose
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"

set -a; . ./.env; set +a
DOMAIN="${DOMAIN:?set DOMAIN in .env}"
EMAIL="${DJANGO_SUPERUSER_EMAIL:-admin@$DOMAIN}"
SERVER_IP="${SERVER_IP:-$(curl -fsS4 https://api.ipify.org || true)}"

COMPOSE="docker compose -f docker-compose.yml"
STAGING=""
for a in "$@"; do
  case "$a" in
    --staging) STAGING="--staging" ;;
    --prod)    COMPOSE="$COMPOSE -f docker-compose.prod.yml" ;;
  esac
done

mkdir -p nginx/certbot-webroot nginx/letsencrypt

echo "==> DNS preflight (public resolvers — this is what Let's Encrypt sees)"
for host in "$DOMAIN" "www.$DOMAIN"; do
  got=""
  for r in 1.1.1.1 8.8.8.8 9.9.9.9; do
    a="$(dig +short A "$host" "@$r" 2>/dev/null | grep -E '^[0-9.]+$' | tail -1 || true)"
    [ -n "$a" ] && got="$a" && break
  done
  if [ "$got" = "$SERVER_IP" ]; then
    echo "   ok $host -> $got"
  else
    echo "   !! $host resolves to '${got:-<none>}', expected $SERVER_IP"
    [ "${FORCE:-0}" = 1 ] || { echo "      wait for propagation, then re-run (or FORCE=1 to skip)."; exit 1; }
    echo "      FORCE=1 set — continuing anyway."
  fi
done

echo "==> making sure nginx is up (HTTP)"
$COMPOSE up -d nginx
sleep 3

echo "==> requesting certificate for $DOMAIN, www.$DOMAIN"
$COMPOSE run --rm --entrypoint certbot certbot \
  certonly --webroot -w /var/www/certbot \
  -d "$DOMAIN" -d "www.$DOMAIN" \
  --email "$EMAIL" --agree-tos --no-eff-email --non-interactive $STAGING

echo "==> enabling HTTPS (nginx restart)"
$COMPOSE restart nginx
sleep 2
echo
echo "done. test: https://$DOMAIN/   https://$DOMAIN/panel/"
