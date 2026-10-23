#!/bin/sh
# Enable the HTTPS vhost when a cert is available. Precedence:
#   1. manually-uploaded pair  /etc/nginx/manual-certs/{fullchain,privkey}.pem
#   2. domain wizard config    /etc/nginx/domain/active.conf (scripts/domain.sh)
#   3. Let's Encrypt           /etc/letsencrypt/live/<domain>/{fullchain,privkey}.pem
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

# a domain set by the domain wizard (scripts/domain.sh, docs/domain.md) wins over
# the .env domain: its generated config holds the new domain + the old one's redirect
if [ "${SRC:-}" != "manual upload" ] && [ -s /etc/nginx/domain/active.conf ]; then
    echo 'include /etc/nginx/domain/active.conf;' > "$OUT"
    echo "[nginx-entrypoint] HTTPS from the domain wizard (/etc/nginx/domain/active.conf)"
elif [ -n "${CERT:-}" ]; then
    export SSL_DOMAIN="${DOMAIN:-_}" SSL_CERT="$CERT" SSL_KEY="$KEY"
    envsubst '${SSL_DOMAIN} ${SSL_CERT} ${SSL_KEY}' < /etc/nginx/ssl.conf.template > "$OUT"
    echo "[nginx-entrypoint] HTTPS enabled for '${DOMAIN:-*}' ($SRC)"
else
    rm -f "$OUT"
    echo "[nginx-entrypoint] no cert for '${DOMAIN:-<unset>}' — HTTP only"
fi

# admin / portal paths (docs/paths.md): scripts/paths.sh writes /etc/nginx/paths/active.conf;
# on a fresh install it doesn't exist yet → the defaults (/panel, /agency)
if [ -f /etc/nginx/paths.conf.template ] && [ ! -s /etc/nginx/paths/active.conf ]; then
    mkdir -p /etc/nginx/paths
    sh /etc/nginx/render-paths.sh /etc/nginx/paths.conf.template /panel /agency > /etc/nginx/paths/active.conf
    echo "[nginx-entrypoint] paths: defaults /panel + /agency"
fi

# reload every 6h to pick up certbot renewals
( while :; do sleep 21600; nginx -s reload 2>/dev/null || true; done ) &

exec "$@"
