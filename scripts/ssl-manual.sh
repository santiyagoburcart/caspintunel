#!/usr/bin/env bash
# Install a manually-obtained TLS certificate (for servers where Let's Encrypt
# HTTP-01 can't run — e.g. filtered networks). Obtain the cert on any machine,
# copy the two PEM files here, run this.
#
#   ./scripts/ssl-manual.sh /path/fullchain.pem /path/privkey.pem
#   ./scripts/ssl-manual.sh            # interactive
#   ./scripts/ssl-manual.sh --prod ...
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"

COMPOSE="docker compose -f docker-compose.yml"
ARGS=()
for a in "$@"; do
  case "$a" in
    --prod) COMPOSE="$COMPOSE -f docker-compose.prod.yml" ;;
    *) ARGS+=("$a") ;;
  esac
done

FULLCHAIN="${ARGS[0]:-}"
KEY="${ARGS[1]:-}"
[ -n "$FULLCHAIN" ] || read -rp "Path to fullchain.pem (cert + intermediates): " FULLCHAIN
[ -n "$KEY" ]       || read -rp "Path to privkey.pem (private key): " KEY

[ -s "$FULLCHAIN" ] || { echo "!! $FULLCHAIN not found"; exit 1; }
[ -s "$KEY" ]       || { echo "!! $KEY not found"; exit 1; }

# validate: parseable, and key matches cert
openssl x509 -in "$FULLCHAIN" -noout >/dev/null || { echo "!! not a valid certificate"; exit 1; }
openssl pkey -in "$KEY" -noout >/dev/null 2>&1 || openssl rsa -in "$KEY" -check -noout >/dev/null 2>&1 \
  || { echo "!! not a valid private key"; exit 1; }
c_mod=$(openssl x509 -in "$FULLCHAIN" -noout -modulus 2>/dev/null | openssl md5)
k_mod=$(openssl pkey -in "$KEY" -pubout 2>/dev/null | openssl md5 || openssl rsa -in "$KEY" -noout -modulus 2>/dev/null | openssl md5)
# fall back to modulus comparison for RSA
if openssl rsa -in "$KEY" -noout -modulus >/dev/null 2>&1; then
  [ "$(openssl x509 -in "$FULLCHAIN" -noout -modulus | openssl md5)" = \
    "$(openssl rsa -in "$KEY" -noout -modulus | openssl md5)" ] \
    || { echo "!! the private key does not match the certificate"; exit 1; }
fi

echo "  subject : $(openssl x509 -in "$FULLCHAIN" -noout -subject | sed 's/subject=//')"
echo "  SANs    : $(openssl x509 -in "$FULLCHAIN" -noout -ext subjectAltName 2>/dev/null | tail -1 | xargs)"
echo "  expires : $(openssl x509 -in "$FULLCHAIN" -noout -enddate | sed 's/notAfter=//')"

mkdir -p nginx/manual-certs
install -m 644 "$FULLCHAIN" nginx/manual-certs/fullchain.pem
install -m 600 "$KEY"       nginx/manual-certs/privkey.pem

echo "==> restarting nginx"
$COMPOSE up -d nginx
$COMPOSE restart nginx
sleep 2
echo "done — nginx now serves HTTPS from the uploaded cert."
