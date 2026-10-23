#!/usr/bin/env bash
# Stand-in for certbot in scripts/test-domain.sh: a self-signed cert with the
# requested names in nginx/letsencrypt/live/<domain>/. FAKE_CERT_BADKEY=1 writes
# a key that does not match the cert (nginx -t then fails → automatic rollback).
set -euo pipefail
d="$1"; shift
san=""; while [ $# -gt 0 ]; do [ "$1" = -d ] && { san="${san:+$san,}DNS:$2"; shift; }; shift; done
dir="${FAKE_LE:?}/live/$d"; mkdir -p "$dir"
openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=$d" -addext "subjectAltName=$san" \
  -keyout "$dir/privkey.pem" -out "$dir/fullchain.pem" >/dev/null 2>&1
[ "${FAKE_CERT_BADKEY:-0}" = 1 ] && openssl genrsa -out "$dir/privkey.pem" 2048 >/dev/null 2>&1
echo "fake certbot: $d ($san)"
