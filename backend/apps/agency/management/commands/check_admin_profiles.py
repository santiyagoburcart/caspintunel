"""v1.35.3: find PasarGuard admins whose subscription header fields are unsafe (invisible / control
characters, non-ASCII in support_url) — they break subscription updates in Happ ("400 Bad Request").

Default = PREVIEW (read-only). --apply re-saves ONLY the unsafe fields with the cleaned value
(admin_crud.clean_field, same as our panel's save). Values that are merely not a link (e.g. "@name",
"hh") are listed for information and never changed here.
"""
import unicodedata

from django.core.management.base import BaseCommand

from apps.agency import admin_crud
from apps.agency.panel_api import agency_panel
from apps.panel.client import PasarGuardClient

KEYS = ("profile_title", "support_url", "sub_domain", "discord_webhook")


def unsafe(k: str, v: str) -> bool:
    if any(unicodedata.category(ch) in ("Cc", "Cf", "Co", "Cs", "Cn", "Zl", "Zp") and ch != admin_crud.ZWNJ for ch in v):
        return True
    if v != v.strip():
        return True
    return k != "profile_title" and not v.isascii()


class Command(BaseCommand):
    help = "Find (and with --apply re-save) admins with header-unsafe profile title / support link."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        panel = agency_panel()
        c = PasarGuardClient(panel)
        r = c._request("GET", "/api/admins", params={"limit": 1000})
        admins = r if isinstance(r, list) else r.get("admins", [])
        fixes = 0
        for a in admins:
            body = {}
            for k in KEYS:
                v = a.get(k) or ""
                if not v:
                    continue
                if unsafe(k, v):
                    try:
                        new = admin_crud.clean_field(k, v)
                    except admin_crud.AdminCrudError:
                        new = admin_crud.clean_compact(v) if k != "profile_title" else admin_crud.clean_text(v)
                    body[k] = new
                    self.stdout.write(f"UNSAFE {a['username']} {k}: {v!r} → {new!r}")
                elif k == "support_url" and not v.startswith(("http://", "https://")):
                    self.stdout.write(f"note   {a['username']} support_url is not a link: {v!r} (left as is)")
            if body:
                fixes += 1
                if opts["apply"]:
                    from urllib.parse import quote

                    admin_crud._gate()
                    c._request("PUT", f"/api/admin/{quote(a['username'], safe='')}", json=body)
                    self.stdout.write(f"   re-saved {a['username']}")
        verb = "re-saved" if opts["apply"] else "would be re-saved (preview — run with --apply)"
        self.stdout.write(f"{fixes} admin(s) {verb}; {len(admins)} checked.")
