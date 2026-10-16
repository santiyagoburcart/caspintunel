"""Admin-panel / reseller-portal paths (docs/paths.md).

The web container never touches nginx: it validates the request and writes
backups/.paths-request.json; the host watcher (scripts/paths.sh apply-request,
cron) renders nginx/paths/active.conf, runs nginx -t, reloads, verifies and
rolls back on failure, then writes backups/.paths-status.json, which this
module reads. The SAME rules live in nginx/render-paths.sh (the final check).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from django.conf import settings
from django.utils import timezone

DEFAULT_ADMIN, DEFAULT_PORTAL = "/panel", "/agency"
_RE = re.compile(r"^/[a-z0-9][a-z0-9_-]{1,39}$")
RESERVED = {"/api", "/admin", "/ws", "/static", "/media", "/_protected_media", "/.well-known", "/assets", "/login",
            "/register", "/reset", "/verify-email", "/terms", "/store", "/checkout", "/history", "/rules", "/profile",
            "/help", "/favicon.svg", "/robots.txt", "/index.html"}


def _dir() -> Path:
    return Path(os.path.dirname(getattr(settings, "UPDATE_SENTINEL_PATH", "/app/backups/.update-requested")))


def request_file() -> Path:
    return _dir() / ".paths-request.json"


def status_file() -> Path:
    return _dir() / ".paths-status.json"


def validate(admin: str, portal: str) -> dict[str, str]:
    errors = {}
    for key, value in (("admin", admin), ("portal", portal)):
        if not _RE.match(value or ""):
            errors[key] = "use / plus 2–40 of a-z 0-9 - _ (e.g. /my-panel)"
        elif value in RESERVED:
            errors[key] = "this path is used by the site"
    if not errors and admin == portal:
        errors["portal"] = "must differ from the admin path"
    if "portal" not in errors and portal == "/panel":
        errors["portal"] = "/panel is kept for the admin panel"
    return errors


def _read(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def state() -> dict:
    last = _read(status_file())
    applied = {"admin": DEFAULT_ADMIN, "portal": DEFAULT_PORTAL}
    if last and last.get("admin") and last.get("portal"):
        applied = {"admin": last["admin"], "portal": last["portal"]}
    return {**applied, "pending": _read(request_file()), "last": last,
            "defaults": {"admin": DEFAULT_ADMIN, "portal": DEFAULT_PORTAL}}


def request_change(admin: str, portal: str, by: str) -> dict:
    data = {"admin": admin, "portal": portal, "requested_by": by, "at": timezone.now().isoformat()}
    path = request_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)
    return data
