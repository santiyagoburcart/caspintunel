#!/bin/sh
# render-paths.sh TEMPLATE ADMIN PORTAL  → nginx config on stdout (POSIX sh: runs in the
# nginx container and on the host). Validates both paths first; exit 2 = invalid.
set -eu
T="$1"; A="$2"; P="$3"
RESERVED=" /api /admin /ws /static /media /_protected_media /.well-known /assets /login /register /reset /verify-email /terms /store /checkout /history /rules /profile /help /favicon.svg /robots.txt /index.html "
valid() {
  case "$1" in *[!a-z0-9/_-]*|*//*|*/) return 1 ;; esac
  printf '%s' "$1" | grep -Eq '^/[a-z0-9][a-z0-9_-]{1,39}$' || return 1
  case "$RESERVED" in *" $1 "*) return 1 ;; esac
  return 0
}
valid "$A" || { echo "invalid admin path: $A" >&2; exit 2; }
valid "$P" || { echo "invalid portal path: $P" >&2; exit 2; }
[ "$A" != "$P" ] || { echo "admin and portal paths must differ" >&2; exit 2; }
[ "$P" != "/panel" ] || { echo "the portal cannot use /panel (the old admin path answers 404)" >&2; exit 2; }
if [ "$A" = "/panel" ]; then LINK="/panel/"; OLD="# admin is on its default path"
else LINK=""; OLD="location = /panel { return 404; }
location ^~ /panel/ { return 404; }"; fi
# OLD may span lines → awk instead of sed for that placeholder
sed -e "s#__ADMIN__#$A#g" -e "s#__PORTAL__#$P#g" -e "s#__ADMIN_LINK__#$LINK#g" "$T" \
  | awk -v old="$OLD" '{ if ($0 == "__OLD_ADMIN__") print old; else print }'
