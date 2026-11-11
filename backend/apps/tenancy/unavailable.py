"""v1.53.2: the page a store's domain shows while the store is not active (draft / suspended / closed).

The host watcher (scripts/tenants_host.py) renders a PARKED vhost for such a store: every path except the ACME challenge
and our /.well-known/caspin/ probe is rewritten to /api/v1/store-unavailable/, which `TenantMiddleware` answers here before
its host check (the store is not active, so the host resolves to no tenant). HTTP 503 + Retry-After, the store's own name
and logo (inlined — nothing else on the domain loads while parked), no data, never our brand. It refreshes itself once a
minute, so a store made active again comes back without a reload. Our own hosts and unknown hosts get 404.
"""
from __future__ import annotations

import base64
import html

from django.http import HttpResponse, HttpResponseNotFound

from . import context

PATH = "/api/v1/store-unavailable/"
LOGO_CAP = 200 * 1024
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
         ".svg": "image/svg+xml", ".ico": "image/x-icon"}


def _store_for(raw_host: str):
    from .models import TenantDomain

    host = (raw_host or "").split(":")[0].strip().lower().rstrip(".")
    bare = host[4:] if host.startswith("www.") else host
    d = (TenantDomain.objects.filter(host__in={host, bare}).exclude(state=TenantDomain.REMOVED)
         .select_related("tenant").first())
    if d is None or d.tenant.is_default:
        return None
    return d.tenant


def _logo(b) -> str:
    f = getattr(b, "logo", None)
    name = getattr(f, "name", "") if f else ""
    if not name:
        return ""
    ext = name[name.rfind("."):].lower() if "." in name else ""
    mime = _MIME.get(ext)
    try:
        if not mime or f.size > LOGO_CAP:
            return ""
        with f.open("rb") as fh:
            return f"data:{mime};base64,{base64.b64encode(fh.read()).decode()}"
    except Exception:  # noqa: BLE001 — a missing file never breaks the page
        return ""


def page(t) -> str:
    from apps.settings_app.models import TenantBranding

    with context.tenant_context(t.pk):
        b = TenantBranding.objects.first()
    fa = (getattr(b, "site_name_fa", "") or t.name or "").strip()
    en = (getattr(b, "site_name_en", "") or fa).strip()
    logo = _logo(b) if b else ""
    e = html.escape
    img = f'<img src="{logo}" alt="" width="72" height="72" style="width:72px;height:72px;object-fit:contain;border-radius:16px">' if logo \
        else f'<div class="mark" aria-hidden="true">{e((fa or en or "?")[:1])}</div>'
    return f"""<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><meta http-equiv="refresh" content="60"><title>{e(fa or en)}</title>
<style>
:root{{color-scheme:light dark;--bg:#f4f6fb;--card:#fff;--text:#111827;--muted:#6b7280;--line:#e5e7eb;--accent:#1464ba}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0b1220;--card:#121a2b;--text:#e6e8ec;--muted:#9aa3b2;--line:#243049;--accent:#5b9bea}}}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;padding:16px;background:var(--bg);
color:var(--text);font-family:Vazirmatn,Tahoma,"Segoe UI",sans-serif;text-align:center}}
.card{{width:100%;max-width:440px;background:var(--card);border:1px solid var(--line);border-radius:20px;padding:28px 22px}}
.mark{{width:72px;height:72px;margin:0 auto;border-radius:16px;display:grid;place-items:center;font-size:32px;font-weight:800;
color:#fff;background:var(--accent)}}h1{{font-size:20px;margin:16px 0 8px}}p{{margin:0;line-height:1.9;color:var(--muted)}}
hr{{border:0;border-top:1px solid var(--line);margin:18px 0}}.en{{font-family:Inter,"Segoe UI",Arial,sans-serif}}
</style></head><body><main class="card">
{img}
<h1>{e(fa)}</h1>
<p>این فروشگاه در حال حاضر در دسترس نیست.</p><p>لطفاً بعداً دوباره سر بزنید.</p>
<hr><div dir="ltr" lang="en" class="en"><h1>{e(en)}</h1><p>This store is not available right now.</p><p>Please check back later.</p></div>
</main></body></html>"""


def respond(request):
    """GET / HEAD /api/v1/store-unavailable/ on a store's own domain (only reached through its parked vhost)."""
    from .models import Tenant

    t = _store_for(request.META.get("HTTP_HOST") or "")
    if t is None:
        return HttpResponseNotFound("unknown site")
    body = page(t)
    resp = HttpResponse("" if request.method == "HEAD" else body, status=503, content_type="text/html; charset=utf-8")
    resp["Retry-After"] = "3600" if t.status in (Tenant.SUSPENDED, Tenant.CLOSED) else "60"
    resp["Cache-Control"] = "no-store"
    resp["X-Robots-Tag"] = "noindex"
    # v1.53.3: an expected 503, not a server error — Django's request logger skips a response already marked as logged
    # (django.utils.log.log_response), so a parked store's visitors never fill the logs with ERROR lines
    resp._has_been_logged = True
    return resp
