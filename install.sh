#!/usr/bin/env bash
# caspintunel — single-command, menu-driven installer / manager.
#
#   ./install.sh                interactive menu
#   ./install.sh --offline      menu, offline mode preselected (air-gapped server)
#
# Menu: 1) Install  2) Update  3) Uninstall  4) Exit
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$ROOT"
ENV_FILE="$ROOT/.env"
VERSION="$(cat "$ROOT/VERSION" 2>/dev/null || echo '?')"
PROJECT="caspintunel"

OFFLINE=0
[ "${1:-}" = "--offline" ] && OFFLINE=1

# ---------------------------------------------------------------- helpers
c()   { printf '\033[%sm%s\033[0m' "$1" "$2"; }
hr()  { printf '%s\n' "────────────────────────────────────────────────────────"; }
ask() { local p="$1" d="${2:-}" a; if [ -n "$d" ]; then read -rp "$p [$d]: " a; echo "${a:-$d}";
        else read -rp "$p: " a; echo "$a"; fi; }
asks(){ local p="$1" a; read -rsp "$p: " a; echo >&2; echo "$a"; }
yes_no(){ local a; read -rp "$1 [y/N] " a; [ "${a:-N}" = y ] || [ "${a:-N}" = Y ]; }

compose() {
  local f=(-f docker-compose.yml -f docker-compose.prod.yml)
  [ "$OFFLINE" = 1 ] && f+=(-f docker-compose.offline.yml)
  docker compose "${f[@]}" "$@"
}
py() { compose exec -T web python manage.py "$@"; }

gen_secret() { python3 -c "import secrets;print(secrets.token_urlsafe(64))"; }
gen_fernet() {
  python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())" 2>/dev/null && return
  [ "$OFFLINE" = 1 ] && { echo "!! cannot generate FIELD_ENCRYPTION_KEY offline (need python-cryptography)"; exit 1; }
  docker run --rm python:3.12-slim sh -c \
    "pip -q install cryptography && python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())'"
}

set_env() {  # set_env KEY VALUE  (creates or replaces the line, value written literally)
  python3 - "$ENV_FILE" "$1" "$2" <<'PY'
import sys
path, key, val = sys.argv[1], sys.argv[2], sys.argv[3]
lines = open(path).read().splitlines() if __import__("os").path.exists(path) else []
done = False
for i, ln in enumerate(lines):
    if ln.startswith(key + "="):
        lines[i] = f"{key}={val}"; done = True; break
if not done:
    lines.append(f"{key}={val}")
open(path, "w").write("\n".join(lines) + "\n")
PY
}

installed() { [ -f "$ENV_FILE" ] && compose ps -a --format '{{.Service}}' 2>/dev/null | grep -q .; }

deployed_version() {
  compose exec -T web sh -c 'cat /app/VERSION 2>/dev/null' 2>/dev/null | tr -d '\r\n' || echo "?"
}

# ---------------------------------------------------------------- install
do_install() {
  hr; echo "$(c '1;36' 'Install')"
  if installed; then
    echo "Already installed (version $(deployed_version)). Use Update or Uninstall."; return
  fi

  if [ "$OFFLINE" = 1 ]; then
    echo "offline mode — images must already be loaded (scripts/load-images.sh)."
    docker image inspect "${PROJECT}-backend" >/dev/null 2>&1 || {
      echo "!! image ${PROJECT}-backend not found. Run: ./scripts/load-images.sh <bundle.tar.gz>"; return; }
  fi

  local DOMAIN SU_USER SU_PASS SU_PASS2 SU_EMAIL DB_PASS DB_ROOT TZ PMA
  DOMAIN=$(ask "Domain (e.g. example.com)")
  [ -n "$DOMAIN" ] || { echo "!! domain is required"; return; }

  echo; echo "Site admin account (you'll log into /panel/ with this):"
  SU_USER=$(ask "  admin username" "admin")
  while :; do
    SU_PASS=$(asks "  admin password")
    SU_PASS2=$(asks "  confirm password")
    [ "$SU_PASS" = "$SU_PASS2" ] && [ -n "$SU_PASS" ] && break
    echo "  passwords don't match / empty — try again"
  done
  SU_EMAIL=$(ask "  admin email")

  echo; echo "Database:"
  DB_PASS=$(asks "  app DB password")
  DB_ROOT=$(asks "  DB root password")

  echo; TZ=$(ask "Timezone" "Asia/Tehran")
  PMA=$(ask "phpMyAdmin port (blank = disabled externally)" "")

  echo; echo "TLS / HTTPS:"
  echo "  1) auto  — Let's Encrypt (needs inbound port 80 reachable from the internet)"
  echo "  2) manual — you upload fullchain.pem + privkey.pem (for filtered networks)"
  local SSL_MODE; SSL_MODE=$(ask "  choice" "1")
  [ "$OFFLINE" = 1 ] && SSL_MODE=2 && echo "  (offline -> manual)"

  # --- write .env ---
  echo; echo "==> writing .env"
  [ -f "$ENV_FILE" ] || cp .env.example "$ENV_FILE"
  set_env PROJECT_NAME        "$PROJECT"
  set_env DOMAIN              "$DOMAIN"
  set_env SERVER_IP           "$(curl -fsS4 https://api.ipify.org 2>/dev/null || echo '')"
  set_env DJANGO_SETTINGS_MODULE config.settings.prod
  set_env DEBUG               false
  set_env ALLOWED_HOSTS       "$DOMAIN,www.$DOMAIN,localhost,127.0.0.1"
  set_env CORS_ALLOWED_ORIGINS "https://$DOMAIN,https://www.$DOMAIN"
  set_env CSRF_TRUSTED_ORIGINS "https://$DOMAIN,https://www.$DOMAIN"
  set_env PUBLIC_BASE_URL     "https://$DOMAIN"
  set_env TIME_ZONE           "$TZ"
  set_env SECRET_KEY          "$(gen_secret)"
  set_env FIELD_ENCRYPTION_KEY "$(gen_fernet)"
  set_env DB_NAME             "$PROJECT"
  set_env DB_USER             "$PROJECT"
  set_env DB_PASSWORD         "$DB_PASS"
  set_env DB_ROOT_PASSWORD    "$DB_ROOT"
  set_env DJANGO_SUPERUSER_USERNAME "$SU_USER"
  set_env DJANGO_SUPERUSER_PASSWORD "$SU_PASS"
  set_env DJANGO_SUPERUSER_EMAIL    "$SU_EMAIL"
  set_env CLOUDFLARE_ZONE     "$DOMAIN"
  set_env EMAIL_HOST          mailserver
  set_env EMAIL_PORT          25
  set_env EMAIL_USE_TLS       false
  set_env DEFAULT_FROM_EMAIL  "no-reply@$DOMAIN"
  [ -n "$PMA" ] && set_env PMA_PORT "$PMA"
  # panel credentials are intentionally NOT collected here
  set_env PANEL_BASE_URL      ""
  set_env PANEL_ADMIN_USERNAME ""
  set_env PANEL_ADMIN_PASSWORD ""
  chmod 600 "$ENV_FILE"
  echo "   .env written (chmod 600, git-ignored)"

  # --- build / start ---
  if [ "$OFFLINE" = 1 ]; then
    echo "==> starting (offline, pre-built images)"
  else
    echo "==> building images"; compose build
  fi
  compose up -d --remove-orphans
  echo "==> waiting for the database"; sleep 10
  py migrate --noinput
  py seed
  set +e; py createsuperuser --noinput 2>/dev/null; set -e

  # --- TLS ---
  case "$SSL_MODE" in
    2) echo; echo "==> manual TLS: run  ./scripts/ssl-manual.sh --prod  with your cert files" ;;
    *) echo; echo "==> Let's Encrypt"; ./scripts/init-letsencrypt.sh --prod || \
         echo "   (couldn't issue yet — set DNS, then: ./scripts/init-letsencrypt.sh --prod)" ;;
  esac

  hr
  echo "$(c '1;32' 'Installed.')  version $VERSION"
  echo "  site   : https://$DOMAIN/"
  echo "  panel  : https://$DOMAIN/panel/   (login: $SU_USER)"
  echo
  echo "$(c '1;33' 'NEXT — Pasargad panel:')"
  echo "  the panel credentials were NOT asked here. Log into the site admin panel"
  echo "  ( https://$DOMAIN/panel/  or  https://$DOMAIN/admin/ ) and enter the"
  echo "  Pasargad panel base URL + admin username/password under the Panel settings."
  echo "  Also set: bot tokens, bank cards, plans, SMS devices."
  hr
}

# ---------------------------------------------------------------- update
do_update() {
  hr; echo "$(c '1;36' 'Update')"
  if ! installed; then echo "$(c '1;31' 'not installed')  — run Install first."; return; fi

  echo "current version: $(deployed_version)"
  if [ "$OFFLINE" = 1 ]; then
    echo "offline — load the new image bundle first (scripts/load-images.sh), then continue."
    yes_no "continue?" || return
  elif [ -d .git ]; then
    echo "==> git pull"; git fetch --all --quiet && git reset --hard '@{upstream}'
  fi

  [ "$OFFLINE" = 1 ] || { echo "==> build"; compose build; }
  echo "==> up";        compose up -d --remove-orphans
  echo "==> migrate + seed"; py migrate --noinput; py seed
  echo "==> collectstatic"; py collectstatic --noinput || true
  rm -f "$ROOT/backups/.update-requested" 2>/dev/null || true
  hr; echo "$(c '1;32' 'Updated.')  now on version $(deployed_version)"
}

# ---------------------------------------------------------------- uninstall
do_uninstall() {
  hr; echo "$(c '1;31' 'Uninstall')"
  if ! installed; then echo "nothing installed."; return; fi
  echo "This stops all containers and DELETES the database and volumes."
  local d; d=$(ask "type the domain to confirm")
  [ -n "$d" ] && grep -q "^DOMAIN=$d$" "$ENV_FILE" 2>/dev/null || { echo "aborted."; return; }

  compose down -v --remove-orphans
  if yes_no "also delete .env, TLS certs, mail data and backups?"; then
    rm -rf "$ENV_FILE" nginx/letsencrypt nginx/manual-certs nginx/certbot-webroot mail backups/*.sql.gz
    echo "   removed."
  fi
  hr; echo "$(c '1;32' 'Uninstalled.')"
}

# ---------------------------------------------------------------- menu
while :; do
  echo; hr
  echo "  $(c '1;36' "$PROJECT")  ·  repo version $VERSION  $( [ "$OFFLINE" = 1 ] && c '1;33' '· OFFLINE MODE' )"
  if installed; then echo "  status: $(c '1;32' installed)  (deployed $(deployed_version))"
  else echo "  status: $(c '1;33' 'not installed')"; fi
  hr
  echo "  1) Install"
  echo "  2) Update"
  echo "  3) Uninstall"
  echo "  4) Exit"
  case "$(ask "  choose" "")" in
    1) do_install ;;
    2) do_update ;;
    3) do_uninstall ;;
    4|q|exit) exit 0 ;;
    "") ;;
    *) echo "  ? pick 1-4" ;;
  esac
done
