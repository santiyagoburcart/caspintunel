#!/bin/sh
# Enable the HTTPS vhost only when a real Let's Encrypt cert is present.
# Runs automatically before nginx starts (nginx image's docker-entrypoint.d).
set -e

DOMAIN="${SSL_DOMAIN:-${DOMAIN:-}}"
CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
OUT="/etc/nginx/conf.d/10-ssl.conf"

if [ -n "$DOMAIN" ] && [ -s "$CERT" ]; then
    export SSL_DOMAIN="$DOMAIN"
    envsubst '${SSL_DOMAIN}' < /etc/nginx/ssl.conf.template > "$OUT"
    echo "[40-ssl] HTTPS enabled for $DOMAIN"
else
    rm -f "$OUT"
    echo "[40-ssl] no cert for '${DOMAIN:-<unset>}' — HTTP only"
fi
