"""v1.57 «گواهی‌های SSL» — the TLS certificates our service depends on, checked daily (beat «ops: SSL certificates») and on
«بررسی الان» (Monitoring). Read-only towards every host: one TLS handshake, nothing else.

Targets (de-duplicated by host + port + SNI):
  site   our domain + www (`settings_app.domain.current_domain`)
  store  every store domain (+ www when the store uses it) — `tenancy.TenantDomain`
  panel  each active PasarGuard panel's host / port
  sub    the hosts customers' subscription links point to (`Service.subscription_url`, every store)
  host   PasarGuard hosts (`GET /api/hosts`): each address (a name, or an IP with its SNI); TLS-configured hosts on their port
         with their SNI, the rest on 443 — a name that serves no certificate there (e.g. a WireGuard / UDP endpoint) is
         `no_tls` (grey, never alerted). PasarGuard nodes are addressed by IP only — nothing to check by name.
Colours: > 30 days green · 14–30 amber · < 14 red · expired / unreachable red. Alerts (Telegram, our staff): at 14 and at
3 days left, and on failure (once per incident, a silent «OK again» after) — never for `no_tls`.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone as dt_tz
from urllib.parse import urlparse

from django.utils import timezone

log = logging.getLogger("caspintunel")
TIMEOUT = 8
SOON, URGENT, LAST = 30, 14, 3
BUSY_KEY = "ops:ssl:busy"
RETRY_DELAY = 3          # v1.57.1: a failed handshake is tried once more after this many seconds (a tunnel blip)
CONFIRM = 2              # v1.57.1: «در دسترس نیست» is alerted only after this many consecutive failed checks
RECHECK_SECONDS = 1800   # … and a first failure queues one extra check this much later (daily checks would wait a day)


def _is_ip(h: str) -> bool:
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def _host_port(url: str, default=443):
    u = urlparse(url if "://" in url else f"https://{url}")
    return (u.hostname or "").lower(), u.port or default


# ------------------------------------------------------------------ targets
def targets() -> dict:
    """{(host, port, sni): {"sources": [...], "expect_tls": bool}} + a note list (what was skipped)."""
    out, notes = {}, []

    def add(host, port, sni, kind, label, expect=True):
        host = (host or "").strip().lower().rstrip(".")
        if not host or host in ("localhost",) or (_is_ip(host) and not sni):
            return
        key = (host, int(port or 443), (sni or "").lower())
        t = out.setdefault(key, {"sources": [], "expect_tls": False})
        if {"kind": kind, "label": label} not in t["sources"]:
            t["sources"].append({"kind": kind, "label": label})
        t["expect_tls"] = t["expect_tls"] or expect

    try:
        from apps.settings_app.domain import current_domain

        d = current_domain()
        if d:
            add(d, 443, "", "site", d)
            add(f"www.{d}", 443, "", "site", f"www.{d}")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"our domain: {exc}"[:120])
    try:
        from apps.tenancy.models import TenantDomain

        for td in TenantDomain.objects.select_related("tenant").filter(state=TenantDomain.ACTIVE):   # only hosts that have a certificate
            add(td.host, 443, "", "store", td.tenant.name)
            if td.include_www and not td.host.startswith("www."):
                add(f"www.{td.host}", 443, "", "store", td.tenant.name)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"store domains: {exc}"[:120])
    try:
        from apps.panel.models import Panel

        for p in Panel.objects.filter(is_active=True):
            h, port = _host_port(p.base_url)
            add(h, port, "", "panel", p.name)
            _pasarguard_hosts(p, add, notes)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"panels: {exc}"[:120])
    try:
        _subscription_hosts(add)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"subscription hosts: {exc}"[:120])
    return {"targets": out, "notes": notes}


def _pasarguard_hosts(panel, add, notes) -> None:
    from apps.panel.services import client_for

    c = client_for(panel)
    try:
        hosts = c._request("GET", "/api/hosts")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"PasarGuard hosts ({panel.name}): {exc}"[:120])
        return
    hosts = hosts if isinstance(hosts, list) else (hosts or {}).get("hosts", [])
    for h in hosts or []:
        if not isinstance(h, dict) or h.get("is_disabled"):
            continue
        addrs = h.get("address") or []
        addrs = addrs if isinstance(addrs, list) else str(addrs).split(",")
        tls = str(h.get("security") or "").lower() == "tls"
        sni = (h.get("sni") or [""]) if isinstance(h.get("sni"), list) else [h.get("sni") or ""]
        sni = next((s for s in sni if s and "*" not in s and "{" not in s), "")
        label = f"{panel.name} · {h.get('remark') or h.get('inbound_tag') or h.get('id')}"
        for a in addrs:
            a = str(a or "").strip()
            if not a or "{" in a or "*" in a:
                continue
            if _is_ip(a) and not sni:
                continue                                    # an IP with no name: no certificate name to check
            add(a, (h.get("port") if tls else None) or 443, sni if _is_ip(a) or (sni and sni != a) else "",
                "host", label, expect=tls)
    try:
        nodes = c._request("GET", "/api/nodes")
        nodes = nodes if isinstance(nodes, list) else (nodes or {}).get("nodes", [])
        named = [n for n in nodes or [] if isinstance(n, dict) and n.get("address") and not _is_ip(str(n["address"]))]
        if not named:
            notes.append(f"{len(nodes or [])} PasarGuard nodes are addressed by IP — no hostname to check")
        for n in named:
            notes.append(f"node {n.get('name')}: uses its own CA (PasarGuard), not a public certificate — skipped")
    except Exception:  # noqa: BLE001 — nodes are informational only
        pass


def _subscription_hosts(add) -> None:
    from apps.panel.models import Service
    from apps.tenancy import context

    seen = set()

    def one():
        for url in Service.objects.exclude(subscription_url="").values_list("subscription_url", flat=True).distinct()[:5000]:
            if "://" in (url or ""):
                h, port = _host_port(url)
                if h and (h, port) not in seen:
                    seen.add((h, port))
                    add(h, port, "", "sub", h)
    context.for_each_tenant(one, name="ssl subscription hosts")


# ------------------------------------------------------------------ one handshake
def probe(host: str, port: int, sni: str = "") -> dict:
    """{ok, issuer, subject, not_after, verified, error, no_tls}. No DB access (runs in a thread)."""
    name = sni or host
    der, verified, verr = None, False, ""
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=name) as tls:
                der = tls.getpeercert(binary_form=True)
                verified = True
    except ssl.SSLCertVerificationError as exc:
        verr = (exc.verify_message or str(exc))[:200]
    except (socket.timeout, TimeoutError) as exc:
        return {"ok": False, "error": f"timeout: {exc}"[:200], "unreachable": True}
    except socket.gaierror as exc:
        return {"ok": False, "error": f"DNS: {exc}"[:200], "unreachable": True}
    except ConnectionRefusedError as exc:
        return {"ok": False, "error": f"refused: {exc}"[:200], "no_tls": True}
    except (ssl.SSLError, OSError) as exc:
        return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"[:200], "no_tls": isinstance(exc, ssl.SSLError)}
    if der is None:                                   # verification failed: read the certificate anyway
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with socket.create_connection((host, port), timeout=TIMEOUT) as sock:
                with ctx.wrap_socket(sock, server_hostname=name) as tls:
                    der = tls.getpeercert(binary_form=True)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": (verr or str(exc))[:200]}
    from cryptography import x509

    cert = x509.load_der_x509_certificate(der)
    na = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after.replace(tzinfo=dt_tz.utc)

    def cn(n):
        attrs = n.get_attributes_for_oid(x509.NameOID.ORGANIZATION_NAME) or n.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
        return attrs[0].value if attrs else n.rfc4514_string()

    return {"ok": True, "issuer": str(cn(cert.issuer))[:255], "subject": str(cn(cert.subject))[:255], "not_after": na,
            "verified": verified, "error": "" if verified else verr}


def probe_twice(host: str, port: int, sni: str = "") -> dict:
    """v1.57.1: probe(), and once more after RETRY_DELAY when the handshake failed (never for a certificate that was read)."""
    import time

    r = probe(host, port, sni)
    if not r.get("ok"):
        time.sleep(RETRY_DELAY)
        r = probe(host, port, sni)
    return r


def classify(days_left, res: dict, expect_tls: bool) -> str:
    if not res.get("ok"):
        return "error" if expect_tls else "no_tls"       # a name not configured for TLS (e.g. WireGuard / UDP) is grey
    if days_left is None or days_left < 0:
        return "expired"
    if not res.get("verified") and res.get("error"):
        return "error" if expect_tls else "no_tls"
    return "ok" if days_left > SOON else "soon" if days_left >= URGENT else "urgent"


# ------------------------------------------------------------------ run
def run(*, alert: bool = True) -> dict:
    from django.core.cache import cache

    from .models import SslCertificate

    cache.set(BUSY_KEY, 1, 600)
    try:
        t = targets()
        items = list(t["targets"].items())
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda kv: probe_twice(kv[0][0], kv[0][1], kv[0][2]), items))
        now = timezone.now()
        keep, recheck = [], False
        for (key, meta), res in zip(items, results):
            host, port, sni = key
            row, _ = SslCertificate.objects.get_or_create(host=host, port=port, sni=sni)
            keep.append(row.pk)
            days = None
            if res.get("ok") and res.get("not_after"):
                days = (res["not_after"] - now).days
            state = classify(days, res, meta["expect_tls"])
            row.sources, row.expect_tls, row.state, row.checked_at = meta["sources"], meta["expect_tls"], state, now
            row.issuer, row.subject = res.get("issuer", "") if res.get("ok") else row.issuer, res.get("subject", "") if res.get("ok") else row.subject
            row.not_after = res.get("not_after") if res.get("ok") else row.not_after
            row.days_left = days if res.get("ok") else row.days_left
            row.verified = bool(res.get("verified"))
            row.error = res.get("error", "")[:300]
            row.failures = row.failures + 1 if state == "error" else 0          # consecutive failed checks
            recheck = recheck or (state == "error" and row.failures < CONFIRM)
            if alert:
                _alert(row)
            row.save()
        SslCertificate.objects.exclude(pk__in=keep).delete()          # a domain that is gone from every source
        out = {"checked": len(items), "notes": t["notes"],
               "states": {s: SslCertificate.objects.filter(state=s).count() for s in ("ok", "soon", "urgent", "expired", "error", "no_tls")}}
        cache.set("ops:ssl:notes", t["notes"], 86400 * 2)
        if recheck and alert:                       # confirm a first failure soon instead of waiting for tomorrow
            _queue_recheck()
            out["recheck_in"] = RECHECK_SECONDS
        return out
    finally:
        cache.delete(BUSY_KEY)


def _queue_recheck() -> None:
    from django.core.cache import cache

    if not cache.add("ops:ssl:recheck", 1, RECHECK_SECONDS):         # one extra check at a time
        return
    try:
        from .tasks import ssl_check_task

        ssl_check_task.apply_async(countdown=RECHECK_SECONDS)
    except Exception as exc:  # noqa: BLE001 — the daily check still runs
        log.warning("ssl re-check not queued: %s", exc)


def _send(text: str, *, silent: bool = False) -> None:
    try:
        from apps.common.staff_alert import alert_staff

        alert_staff(text, perm="monitoring.view", platform=True, silent=silent)
    except Exception as exc:  # noqa: BLE001 — an alert outage never stops the check
        log.warning("ssl alert failed: %s", exc)


def _name(row) -> str:
    return row.host + (f":{row.port}" if row.port != 443 else "") + (f" (SNI {row.sni})" if row.sni else "")


def _alert(row) -> None:
    """Once per level per certificate: 14 days, 3 days, failure (-1); renewed / fixed → back to 0 (+ a silent note).
    v1.57.1: «در دسترس نیست» only after CONFIRM consecutive failed checks (each check already retried the handshake once);
    an expired certificate and the 14 / 3-day alerts are unchanged."""
    from apps.common.jalali import to_jalali_str

    who = "، ".join(s["label"] for s in row.sources[:3])
    if row.state == "no_tls":
        return
    if row.state == "error" and row.failures < CONFIRM:
        row.failing_since = row.failing_since or timezone.now()
        return                                      # v1.57.1: one failed check may be a blip — wait for the next one
    if row.state in ("error", "expired"):
        if row.alerted != -1:
            row.failing_since = row.failing_since or timezone.now()
            why = "منقضی شده" if row.state == "expired" else f"در دسترس نیست / خطا: {row.error[:120]}"
            _send(f"🔒❌ گواهی SSL «{_name(row)}» — {why}\n{who}")
            row.alerted = -1
        return
    if row.alerted != -1:
        row.failing_since = None                    # a blip that never alerted: nothing to announce
    if row.alerted == -1:
        _send(f"🔒✅ گواهی SSL «{_name(row)}» دوباره سالم است ({row.days_left} روز مانده).", silent=True)
        row.alerted, row.failing_since = 0, None
    d = row.days_left if row.days_left is not None else 999
    level = LAST if d <= LAST else URGENT if d <= URGENT else 0
    if level == 0:
        row.alerted = 0                                   # renewed: the next expiry alerts again
    elif row.alerted == 0 or level < row.alerted:
        until = to_jalali_str(row.not_after, "%Y/%m/%d") if row.not_after else "?"
        _send(f"🔒⚠️ گواهی SSL «{_name(row)}» {d} روز دیگر منقضی می‌شود ({until}) — صادرکننده: {row.issuer or '?'}\n{who}")
        row.alerted = level


def rows() -> tuple[list[dict], list, bool]:
    from django.core.cache import cache

    from .models import SslCertificate

    order = {"expired": 0, "error": 1, "urgent": 2, "soon": 3, "ok": 4, "no_tls": 5}
    out = [{"id": r.id, "host": r.host, "port": r.port, "sni": r.sni, "sources": r.sources, "expect_tls": r.expect_tls,
            "state": r.state, "issuer": r.issuer, "subject": r.subject, "not_after": r.not_after, "days_left": r.days_left,
            "verified": r.verified, "error": r.error, "checked_at": r.checked_at, "failing_since": r.failing_since}
           for r in SslCertificate.objects.all()]
    out.sort(key=lambda r: (order.get(r["state"], 9), r["days_left"] if r["days_left"] is not None else 99999, r["host"]))
    return out, cache.get("ops:ssl:notes") or [], bool(cache.get(BUSY_KEY))
