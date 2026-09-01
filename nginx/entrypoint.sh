#!/bin/sh
# Enable the HTTPS vhost when a cert is available. Precedence:
#   1. manually-uploaded pair  /etc/nginx/manual-certs/{fullchain,privkey}.pem
#   2. Let's Encrypt           /etc/letsencrypt/live/<domain>/{fullchain,privkey}.pem
# A missing cert never stops nginx — it just serves HTTP.
set -e

DOMAIN="${SSL_DOMAIN:-}"
MAN_CERT="/etc/nginx/manual-certs/fullchain.pem"
MAN_KEY="/etc/nginx/manual-certs/privkey.pem"
LE_CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
LE_KEY="/etc/letsencrypt/live/${DOMAIN}/privkey.pem"
OUT="/etc/nginx/conf.d/10-ssl.conf"

if [ -s "$MAN_CERT" ] && [ -s "$MAN_KEY" ]; then
    CERT="$MAN_CERT"; KEY="$MAN_KEY"; SRC="manual upload"
elif [ -n "$DOMAIN" ] && [ -s "$LE_CERT" ] && [ -s "$LE_KEY" ]; then
    CERT="$LE_CERT"; KEY="$LE_KEY"; SRC="Let's Encrypt"
fi

if [ -n "${CERT:-}" ]; then
    export SSL_DOMAIN="${DOMAIN:-_}" SSL_CERT="$CERT" SSL_KEY="$KEY"
    envsubst '${SSL_DOMAIN} ${SSL_CERT} ${SSL_KEY}' < /etc/nginx/ssl.conf.template > "$OUT"
    echo "[nginx-entrypoint] HTTPS enabled for '${DOMAIN:-*}' ($SRC)"
else
    rm -f "$OUT"
    echo "[nginx-entrypoint] no cert for '${DOMAIN:-<unset>}' — HTTP only"
fi

# reload every 6h to pick up certbot renewals
( while :; do sleep 21600; nginx -s reload 2>/dev/null || true; done ) &

exec "$@"
