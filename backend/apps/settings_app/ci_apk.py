"""The CI-built Android SMS Bridge APK (v1.48, .github/workflows/android-release.yml).

Every `v*` tag builds a signed release APK and attaches it to that GitHub release as `SmsBridge-<versionName>.apk`.
This server copies the newest one into MEDIA_ROOT/apps/ci/ (nginx 404s /media/apps/) and serves it itself, so the
Apps page works on Iran-only hosts and a store never sees where it came from. Never redirect a browser to GitHub.

Download order (adminpanel/views/apps.py): uploaded file > this CI copy > the bundled debug APK in the repo.
Best effort: any GitHub problem means "no CI APK" (cached for a few minutes), never an error page.
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from django.conf import settings

log = logging.getLogger("caspintunel")

ASSET_RE = re.compile(r"^SmsBridge-(\d+(?:\.\d+){1,3})\.apk$")
MAX_BYTES = 60 * 1024 * 1024
CACHE_KEY = "apps:ci_apk:latest"
CACHE_TTL = 600            # a found release
FAIL_TTL = 300             # nothing / GitHub unreachable
LOCK_KEY = "apps:ci_apk:lock"


def ci_dir() -> Path:
    return Path(settings.MEDIA_ROOT) / "apps" / "ci"


def _headers(accept: str) -> dict:
    h = {"Accept": accept, "User-Agent": "caspintunel-apps"}
    token = getattr(settings, "GITHUB_TOKEN", "")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def latest() -> dict | None:
    """{name, version, size, tag, api_url, digest} of the newest release APK, or None. Cached."""
    from django.core.cache import cache

    hit = cache.get(CACHE_KEY)
    if hit is not None:
        return hit or None
    found = None
    owner, repo = getattr(settings, "GITHUB_OWNER", ""), getattr(settings, "GITHUB_REPO", "")
    if owner and repo and getattr(settings, "CI_APK_FROM_GITHUB", True):
        try:
            import requests

            r = requests.get(f"https://api.github.com/repos/{owner}/{repo}/releases/latest",
                             headers=_headers("application/vnd.github+json"), timeout=5)
            if r.status_code == 200:
                data = r.json()
                for a in data.get("assets") or []:
                    m = ASSET_RE.match(a.get("name") or "")
                    if m and 0 < int(a.get("size") or 0) <= MAX_BYTES:
                        found = {"name": a["name"], "version": m.group(1), "size": int(a["size"]),
                                 "tag": data.get("tag_name") or "", "api_url": a.get("url") or "",
                                 "digest": a.get("digest") or ""}
                        break
        except Exception as exc:  # noqa: BLE001 — best effort
            log.info("ci apk: GitHub lookup failed: %s", exc)
    cache.set(CACHE_KEY, found or {}, CACHE_TTL if found else FAIL_TTL)
    return found


def _download(info: dict, dest: Path) -> bool:
    import requests

    tmp = dest.with_suffix(".part")
    sha = hashlib.sha256()
    size = 0
    try:
        with requests.get(info["api_url"], headers=_headers("application/octet-stream"), stream=True, timeout=30) as r:
            r.raise_for_status()
            with tmp.open("wb") as f:
                for chunk in r.iter_content(256 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("too large")
                    sha.update(chunk)
                    f.write(chunk)
        want = info.get("digest") or ""
        if size != info["size"] or (want.startswith("sha256:") and want[7:] != sha.hexdigest()):
            raise ValueError(f"size/digest mismatch ({size} bytes)")
        tmp.replace(dest)
        return True
    except Exception as exc:  # noqa: BLE001 — best effort
        log.warning("ci apk: download of %s failed: %s", info.get("name"), exc)
        tmp.unlink(missing_ok=True)
        return False


def local_file() -> Path | None:
    """The newest CI APK on this server, fetching the latest release's copy first when it is missing."""
    from django.core.cache import cache

    d = ci_dir()
    info = latest()
    if info:
        dest = d / info["name"]
        if not dest.is_file() and cache.add(LOCK_KEY, 1, 120):
            try:
                d.mkdir(parents=True, exist_ok=True)
                if _download(info, dest):
                    for old in d.glob("SmsBridge-*.apk"):
                        if old != dest:
                            old.unlink(missing_ok=True)
            finally:
                cache.delete(LOCK_KEY)
        if dest.is_file():
            return dest
    have = sorted(d.glob("SmsBridge-*.apk"), key=lambda p: p.stat().st_mtime, reverse=True) if d.is_dir() else []
    return have[0] if have else None
