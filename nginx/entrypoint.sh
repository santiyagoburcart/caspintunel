#!/bin/sh
# Enable the HTTPS vhost only when a Let's Encrypt cert exists (a missing cert
# never stops nginx), then run nginx with a background reload loop so renewed
# certs are picked up without a restart.
set -e

DOMAIN="${SSL_DOMAIN:-}"
CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
OUT="/etc/nginx/conf.d/10-ssl.conf"

if [ -n "$DOMAIN" ] && [ -s "$CERT" ]; then
    export SSL_DOMAIN="$DOMAIN"
    envsubst '${SSL_DOMAIN}' < /etc/nginx/ssl.conf.template > "$OUT"
    echo "[nginx-entrypoint] HTTPS enabled for $DOMAIN"
else
    rm -f "$OUT"
    echo "[nginx-entrypoint] no cert for '${DOMAIN:-<unset>}' — HTTP only"
fi

# reload every 6h to pick up certbot renewals
( while :; do sleep 21600; nginx -s reload 2>/dev/null || true; done ) &

exec "$@"
