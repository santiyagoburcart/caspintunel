"""Admin "Documentation" page: the repo's docs/*.md, read-only.

GET /admin/docs/            [{slug, title}] (docs/README.md first)
GET /admin/docs/<slug>/     {slug, title, markdown}

Only plain `docs/*.md` files are served (no sub-directories, no other files),
and any `NAME=value` line whose name looks like a secret is masked, so a real
value pasted into a doc by mistake never reaches the browser.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from .base import AdminAPIView

SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SECRET_LINE = re.compile(
    r"^(\s*(?:export\s+)?[A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY|ENCRYPTION_KEY)[A-Z0-9_]*\s*[=:]\s*)(\S.*)$",
    re.M)
PLACEHOLDER = re.compile(r"^(?:x+|\*+|•+|\.\.\.|<[^>]*>|\$\{?[A-Z_]+\}?|change-?me|your[-_].*|\"\"|''|)$", re.I)
HIDDEN = {"security-review"}       # internal review notes stay in the repo


def _dir() -> Path:
    return Path(settings.DOCS_DIR)


def _title(text: str, slug: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return slug


def mask_secrets(text: str) -> str:
    def repl(m):
        value = m.group(2).strip()
        return m.group(0) if PLACEHOLDER.match(value) else m.group(1) + "••••••••"
    return SECRET_LINE.sub(repl, text)


def _files() -> list[Path]:
    d = _dir()
    if not d.is_dir():
        return []
    files = [p for p in d.glob("*.md") if p.is_file() and SLUG.match(p.stem.lower()) and p.stem.lower() not in HIDDEN]
    return sorted(files, key=lambda p: (p.stem.lower() != "readme", p.stem.lower()))


class DocsListView(AdminAPIView):
    perms_map = {"GET": ["settings.manage"]}

    @extend_schema(summary="Documentation pages (docs/*.md)")
    def get(self, request):
        return Response([{"slug": p.stem.lower(), "title": _title(p.read_text(encoding="utf-8"), p.stem)}
                         for p in _files()])


class DocsPageView(AdminAPIView):
    perms_map = {"GET": ["settings.manage"]}

    @extend_schema(summary="One documentation page as markdown")
    def get(self, request, slug):
        page = next((p for p in _files() if p.stem.lower() == slug), None)
        if page is None:
            raise Http404
        text = mask_secrets(page.read_text(encoding="utf-8"))
        return Response({"slug": slug, "title": _title(text, page.stem), "markdown": text})
