"""Store domains + TLS (multi-tenant Phase 3, docs/multi-tenant.md §7). Only OUR staff add / change / remove a store's domain
(Agency → admin → «فروشگاه»); the reseller sees the state read-only in their store panel.

A domain walks through:

  pending_dns   we show the exact records for the reseller's Cloudflare — A <host> → our Finland IP (mode *direct*) or our
                Iran IP (mode *tunnel*), the same for www, and TXT _caspin-verify.<host> = token. `check_dns` (Celery, every
                5 min, or «بررسی الان») needs the TXT token AND the A record on our IP — or, proxied by their Cloudflare,
                Cloudflare edges plus an HTTP probe of /.well-known/caspin/<token> that must reach THIS server.
  cert_pending  the host watcher (scripts/tenants.sh, cron every minute on the host) gets the host from
                backups/.tenant-domains.json: it first fetches a probe file through the PUBLIC path (proves Let's Encrypt
                will reach us — direct, through the Iran tunnel without PROXY protocol, or through their Cloudflare), then
                issues an HTTP-01 certificate (webroot, served on 80 and 443 for every host), renders nginx/tenants/<host>.conf,
                nginx -t, reloads, verifies over TLS and rolls back on failure. Results: backups/.tenant-status.json.
  active        TLS health over the public path passes → the store answers on the host (middleware + ALLOWED_HOSTS).
                Health every 5 min, DNS daily, certificate expiry alert at 14 days (renewal = the certbot container's
                `certbot renew`, nginx reloads every 6 h).
  failed        3 certificate attempts failed (Let's Encrypt limits) — «تلاش دوباره» puts it back.
  removed       nginx file + certificate are removed by the watcher; the row stays for the audit trail.

The container never touches nginx or certbot itself (same rule as scripts/domain.sh).
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.models import write_audit

from .models import Tenant, TenantDomain

log = logging.getLogger("caspintunel")

VERIFY_PREFIX = "_caspin-verify"
PROBE_PATH = "/.well-known/caspin/"
CHECK_EVERY = timedelta(minutes=5)          # pending DNS / health
DNS_RECHECK = timedelta(days=1)             # active domains: still pointing at us?
MAX_CERT_FAILURES = 3
EXPIRY_ALERT_DAYS = 14
LIVE = (TenantDomain.PENDING_DNS, TenantDomain.VERIFIED, TenantDomain.CERT_PENDING, TenantDomain.ACTIVE, TenantDomain.FAILED)
MODES = (TenantDomain.DIRECT, TenantDomain.TUNNEL)


class DomainError(Exception):
    def __init__(self, en: str, fa: str, status: int = 400, field: str | None = "host"):
        super().__init__(en)
        self.en, self.fa, self.status, self.field = en, fa, status, field


# ------------------------------------------------------------------ input
def clean_host(raw: str) -> str:
    """store.example (lowercase, punycode, no scheme / path / port / www.) — or DomainError."""
    from apps.settings_app import domain as D

    h = D.normalize(raw)
    if not h:
        raise DomainError("enter a domain name", "نام دامنه را وارد کنید")
    try:
        ipaddress.ip_address(h)
        raise DomainError("enter a domain name, not an IP address", "نام دامنه وارد کنید، نه آدرس IP")
    except ValueError:
        pass
    if len(h) > 253 or not D._DOMAIN_RE.match(h):
        raise DomainError(f"{h} is not a valid domain name", f"{h} نام دامنهٔ معتبری نیست")
    from .middleware import own_hosts

    ours = {x for x in own_hosts() if "." in x}
    if h in ours or any(h == f"mail.{o}" for o in ours):
        raise DomainError(f"{h} is our own domain", f"{h} دامنهٔ خود ماست")
    return h


def target_ip(mode: str) -> str:
    """The A record the reseller creates: our Finland IP (direct) or our Iran IP (tunnel)."""
    if mode == TenantDomain.TUNNEL:
        from apps.settings_app.models import DomainConfig

        ips = list(DomainConfig.load().iran_ips or [])
        return ips[0] if ips else ""
    ip = (getattr(settings, "SERVER_IP", "") or "").strip()
    if not ip:
        from apps.settings_app import domain as D

        ip = D.server_ip()
    return ip


def instructions(d: TenantDomain) -> dict:
    """What we send the reseller (copyable in «فروشگاه»)."""
    ip = target_ip(d.mode)
    recs = [{"type": "A", "name": d.host, "value": ip, "proxy": "dns_only_or_proxied"}]
    if d.include_www:
        recs.append({"type": "A", "name": f"www.{d.host}", "value": ip, "proxy": "dns_only_or_proxied"})
    recs.append({"type": "TXT", "name": f"{VERIFY_PREFIX}.{d.host}", "value": d.verify_token, "proxy": "dns_only"})
    return {"ip": ip, "mode": d.mode, "records": recs,
            "cloudflare_ssl": "full",                # proxied: SSL/TLS mode Full; Full (strict) only once the certificate exists
            "ttl": 60}


# ------------------------------------------------------------------ staff actions (Agency → admin → «فروشگاه»)
def _audit(action: str, d: TenantDomain, staff, **detail) -> None:
    write_audit(action=action, staff=staff, target=d, detail={"host": d.host, "tenant": d.tenant_id, **detail})


def _forget(d: TenantDomain) -> None:
    from django.core.cache import cache

    from .middleware import forget_hosts

    forget_hosts(d.tenant_id)
    cache.delete("dynamic_allowed_hosts")                   # apps.common.middleware re-reads the active hosts
    transaction.on_commit(lambda: (forget_hosts(d.tenant_id), cache.delete("dynamic_allowed_hosts")))


@transaction.atomic
def add(tenant: Tenant, raw_host: str, *, mode: str = TenantDomain.DIRECT, include_www: bool = True, staff=None) -> TenantDomain:
    if tenant.is_default:
        raise DomainError("our own store's domain is changed in Settings → Domain", "دامنهٔ فروشگاه اصلی از تنظیمات دامنه عوض می‌شود",
                          403, None)
    if mode not in MODES:
        raise DomainError("mode must be direct or tunnel", "حالت باید مستقیم یا تونل ایران باشد", field="mode")
    host = clean_host(raw_host)
    if mode == TenantDomain.TUNNEL and not target_ip(mode):
        raise DomainError("no Iran IP is set (Settings → Domain → access mode)", "آی‌پی ایران تنظیم نشده (تنظیمات دامنه → حالت دسترسی)",
                          field="mode")
    old = TenantDomain.objects.select_for_update().filter(host=host).first()
    if old is not None and old.state != TenantDomain.REMOVED:
        same = old.tenant_id == tenant.id
        raise DomainError(f"{host} is already {'on this store' if same else 'used by another store'}",
                          f"{host} {'قبلاً برای همین فروشگاه ثبت شده' if same else 'برای فروشگاه دیگری ثبت شده'}", 409)
    if old is not None:
        old.delete()                                         # a removed row of the same host: start clean (new token)
    d = TenantDomain.objects.create(tenant=tenant, host=host, mode=mode, include_www=bool(include_www),
                                    state=TenantDomain.PENDING_DNS)
    _audit("store.domain_added", d, staff, mode=mode, www=d.include_www)
    return d


@transaction.atomic
def update(d: TenantDomain, *, mode: str | None = None, include_www: bool | None = None, staff=None) -> TenantDomain:
    d = TenantDomain.objects.select_for_update().get(pk=d.pk)
    if d.state == TenantDomain.REMOVED:
        raise DomainError("this domain was removed", "این دامنه حذف شده", 409, None)
    before = {"mode": d.mode, "www": d.include_www}
    if mode is not None:
        if mode not in MODES:
            raise DomainError("mode must be direct or tunnel", "حالت باید مستقیم یا تونل ایران باشد", field="mode")
        if mode == TenantDomain.TUNNEL and not target_ip(mode):
            raise DomainError("no Iran IP is set (Settings → Domain → access mode)", "آی‌پی ایران تنظیم نشده", field="mode")
        d.mode = mode
    if include_www is not None:
        d.include_www = bool(include_www)
    after = {"mode": d.mode, "www": d.include_www}
    if after == before:
        return d
    if d.state != TenantDomain.ACTIVE:
        d.state = TenantDomain.PENDING_DNS                   # check the new records first
        d.verified_at = None
    elif after["www"] != before["www"]:
        d.state, d.cert_failures = TenantDomain.CERT_PENDING, 0     # the certificate must (no longer) cover www
    d.last_check_at = None                                   # re-check on the next tick
    d.save()
    _audit("store.domain_updated", d, staff, before=before, after=after)
    write_desired()
    _forget(d)
    return d


@transaction.atomic
def remove(d: TenantDomain, *, staff=None) -> TenantDomain:
    d = TenantDomain.objects.select_for_update().get(pk=d.pk)
    if d.state == TenantDomain.REMOVED:
        return d
    prev = d.state
    d.state, d.last_error = TenantDomain.REMOVED, ""
    d.save(update_fields=["state", "last_error", "updated_at"])
    _audit("store.domain_removed", d, staff, previous_state=prev)
    write_desired()
    _forget(d)
    return d


@transaction.atomic
def retry(d: TenantDomain, *, staff=None) -> TenantDomain:
    """«بررسی الان / تلاش دوباره»: DNS again now; a failed certificate is tried again (fresh attempts)."""
    d = TenantDomain.objects.select_for_update().get(pk=d.pk)
    if d.state == TenantDomain.REMOVED:
        raise DomainError("this domain was removed", "این دامنه حذف شده", 409, None)
    if d.state == TenantDomain.FAILED:
        d.state = TenantDomain.CERT_PENDING if d.verified_at else TenantDomain.PENDING_DNS
    d.cert_failures, d.retry_token, d.last_check_at = 0, d.retry_token + 1, None
    d.save()
    _audit("store.domain_retry", d, staff, state=d.state)
    write_desired()
    return d


# ------------------------------------------------------------------ checks
def _txt_values(name: str) -> tuple[list[str], list[dict]]:
    from apps.settings_app import domain as D

    res = D.resolve(name, "TXT")
    vals = sorted({v.strip().strip('"').replace('" "', "") for r in res["resolvers"] for v in r["ips"]})
    return vals, res["resolvers"]


def _a_check(name: str, want: str) -> dict:
    from apps.settings_app import domain as D
    from apps.settings_app.access import is_cloudflare_ip

    res = D.resolve(name, "A")
    answered = [r for r in res["resolvers"] if "error" not in r and r["ips"]]
    seen = sorted({i for r in answered for i in r["ips"]})
    proxied = bool(seen) and all(is_cloudflare_ip(i) for i in seen)
    ok = bool(answered) and bool(want) and all(set(r["ips"]) == {want} for r in answered)
    return {"name": name, "ok": ok, "seen": seen, "expected": want, "proxied": proxied,
            "errors": [r["resolver"] for r in res["resolvers"] if "error" in r]}


def reach(host: str, token: str, *, scheme: str = "http", timeout: float = 10) -> dict:
    """GET <scheme>://<host>/.well-known/caspin/<token> through the PUBLIC path (whatever DNS says — their Cloudflare, the
    Iran tunnel or us): it must come back from THIS server (body = token, our instance header)."""
    import requests

    from apps.settings_app.access import instance_id

    url = f"{scheme}://{host}{PROBE_PATH}{token}"
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True, headers={"User-Agent": "caspin-domain-check"},
                         verify=getattr(settings, "DOMAIN_ACCESS_VERIFY_TLS", True))
    except requests.RequestException as exc:
        return {"ok": False, "url": url, "error": f"no answer — {exc.__class__.__name__}: {str(exc)[:160]}"}
    mine = r.headers.get("X-Caspin-Instance") == instance_id()
    ok = r.status_code == 200 and mine and r.text.strip() == token
    err = "" if ok else (f"HTTP {r.status_code}" + ("" if mine else " from something that is not this server"))
    return {"ok": ok, "url": url, "status": r.status_code, "final_url": r.url, "error": err}


def check_dns(d: TenantDomain) -> dict:
    want = target_ip(d.mode)
    txt, _ = _txt_values(f"{VERIFY_PREFIX}.{d.host}")
    out = {"at": timezone.now().isoformat(), "txt": {"name": f"{VERIFY_PREFIX}.{d.host}", "ok": d.verify_token in txt,
                                                     "seen": txt[:5]},
           "a": _a_check(d.host, want)}
    if d.include_www:
        out["www"] = _a_check(f"www.{d.host}", want)
    proxied = out["a"]["proxied"]
    out["proxied"] = proxied
    names_ok = all(x["ok"] or x["proxied"] for x in [out["a"]] + ([out["www"]] if d.include_www else []))
    if proxied or (d.include_www and out["www"]["proxied"]):
        out["reach"] = reach(d.host, d.verify_token)          # we cannot see the origin behind their Cloudflare
        names_ok = names_ok and out["reach"]["ok"]
    out["ok"] = out["txt"]["ok"] and names_ok
    return out


def health(d: TenantDomain) -> dict:
    """TLS through the public path: our IP for the mode (DNS-only), or what their DNS answers (proxied). Valid certificate
    for the host, the probe answered by THIS server for THIS domain, and once active the store's /api/v1/health/."""
    from apps.settings_app.access import probe

    ip = target_ip(d.mode)
    if d.proxied:
        seen = (d.dns.get("a") or {}).get("seen") or []
        ip = seen[0] if seen else ip
    r = probe(ip, d.host, f"{PROBE_PATH}{d.verify_token}")
    out = {"at": timezone.now().isoformat(), "ip": ip, "ok": r["ok"] and (r.get("data") or "").strip() == d.verify_token,
           "status": r.get("status"), "ms": r.get("ms"), "error": r.get("error", "")}
    if out["ok"] and d.state == TenantDomain.ACTIVE:
        a = probe(ip, d.host)
        out["api"] = {"ok": a["ok"], "status": a.get("status"), "error": a.get("error", "")}
        out["ok"] = a["ok"]
        if not a["ok"]:
            out["error"] = a.get("error") or f"/api/v1/health/ answered {a.get('status')}"
    return out


# ------------------------------------------------------------------ files shared with the host watcher
def _dir():
    from apps.settings_app import domain as D

    return D._dir()


def desired_file():
    return _dir() / ".tenant-domains.json"


def status_file():
    return _dir() / ".tenant-status.json"


def desired() -> list[dict]:
    """What the host watcher works on: every verified, not failed / removed domain (certificate + nginx file)."""
    rows = (TenantDomain.objects.filter(state__in=(TenantDomain.CERT_PENDING, TenantDomain.ACTIVE), verified_at__isnull=False)
            .select_related("tenant").order_by("id"))
    return [{"host": d.host, "www": d.include_www, "tenant": d.tenant_id, "retry": d.retry_token,
             "probe": f"{PROBE_PATH}{d.verify_token}", "token": d.verify_token} for d in rows]


def write_desired() -> None:
    data = {"at": timezone.now().isoformat(), "email": getattr(settings, "LETSENCRYPT_EMAIL", "") or "",
            "hosts": desired()}
    path = desired_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads(path.read_text()) if path.exists() else None
        if old and old.get("hosts") == data["hosts"]:
            return
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
        os.replace(tmp, path)
    except OSError as exc:                                  # never fail a staff action on the shared file
        log.warning("tenant domains: could not write %s: %s", path, exc)


def host_status() -> dict:
    try:
        return json.loads(status_file().read_text()).get("hosts") or {}
    except (OSError, ValueError):
        return {}


def _dt(v):
    from django.utils.dateparse import parse_datetime

    return parse_datetime(v) if isinstance(v, str) and v else None


# ------------------------------------------------------------------ the tick (Celery, every minute)
def _alert(text: str, key: str, ttl: int = 86400) -> None:
    from apps.common.staff_alert import alert_staff

    transaction.on_commit(lambda: alert_staff(text, perm="agency.manage", platform=True, dedupe_key=key, ttl=ttl))


def _step_pending(d: TenantDomain, now) -> None:
    if d.last_check_at and now - d.last_check_at < CHECK_EVERY:
        return
    res = check_dns(d)
    d.dns, d.last_check_at, d.proxied = res, now, bool(res.get("proxied"))
    if res["ok"]:
        d.state, d.verified_at, d.last_error, d.cert_failures = TenantDomain.CERT_PENDING, now, "", 0
        _audit("store.domain_verified", d, "system", proxied=d.proxied)
    else:
        d.last_error = dns_problem(res)[:500]
    d.save()


def dns_problem(res: dict) -> str:
    bits = []
    if not res.get("txt", {}).get("ok"):
        bits.append(f"TXT {res.get('txt', {}).get('name')} not found")
    for k in ("a", "www"):
        x = res.get(k)
        if x and not (x["ok"] or x["proxied"]):
            bits.append(f"A {x['name']} = {', '.join(x['seen']) or 'nothing'} (expected {x['expected']})")
    if res.get("reach") and not res["reach"]["ok"]:
        bits.append(f"{res['reach']['url']}: {res['reach']['error']}")
    return "; ".join(bits)


def _step_cert(d: TenantDomain, st: dict, now) -> None:
    if st.get("retry", d.retry_token) != d.retry_token:
        return                                               # the watcher has not seen the latest retry yet
    if st.get("cert_ok") and st.get("nginx_ok"):
        d.cert_expires_at = _dt(st.get("cert_expires")) or d.cert_expires_at
        h = health(d)
        d.health, d.last_check_at = h, now
        if h["ok"]:
            d.state, d.cert_issued_at, d.last_error, d.unhealthy_since = TenantDomain.ACTIVE, now, "", None
            d.save()
            _audit("store.domain_active", d, "system", expires=st.get("cert_expires"))
            _forget(d)
            _alert(f"✅ دامنهٔ فروشگاه فعال شد: {d.host} (فروشگاه {d.tenant.name})\nStore domain is live: {d.host}",
                   f"tenant-domain:active:{d.pk}")
            return
        d.last_error = f"health: {h['error']}"[:500]
        d.save()
        return
    tried = st.get("cert_tried_at") or st.get("challenge_at") or ""
    err = st.get("cert_error") or st.get("challenge_error") or st.get("nginx_error") or ""
    if err and tried and tried != (d.health or {}).get("seen_failure"):
        d.health = {**(d.health or {}), "seen_failure": tried}
        d.last_error = err[:500]
        if st.get("cert_error"):                            # only real Let's Encrypt attempts count (pre-check failures are free)
            d.cert_failures += 1
        if d.cert_failures >= MAX_CERT_FAILURES:
            d.state = TenantDomain.FAILED
            _audit("store.domain_failed", d, "system", error=err[:300])
            _alert(f"⚠️ گواهی دامنهٔ {d.host} صادر نشد ({d.cert_failures} بار): {err[:200]}\n"
                   f"Store domain certificate failed: {d.host}", f"tenant-domain:failed:{d.pk}")
        d.save()


def _step_active(d: TenantDomain, st: dict, now) -> None:
    if st.get("cert_expires"):
        d.cert_expires_at = _dt(st["cert_expires"]) or d.cert_expires_at
    if d.last_check_at and now - d.last_check_at < CHECK_EVERY:
        d.save(update_fields=["cert_expires_at", "updated_at"])
        return
    h = health(d)
    d.health, d.last_check_at = h, now
    if h["ok"]:
        if d.unhealthy_since:
            _audit("store.domain_recovered", d, "system")
        d.unhealthy_since, d.last_error = None, ""
    else:
        d.unhealthy_since = d.unhealthy_since or now
        d.last_error = f"health: {h['error']}"[:500]
        if now - d.unhealthy_since >= timedelta(minutes=30):
            _alert(f"⚠️ دامنهٔ فروشگاه {d.host} از نیم ساعت پیش در دسترس نیست: {h['error'][:200]}\n"
                   f"Store domain unreachable for 30+ min: {d.host}", f"tenant-domain:down:{d.pk}", ttl=6 * 3600)
    if d.cert_expires_at and d.cert_expires_at - now < timedelta(days=EXPIRY_ALERT_DAYS):
        days = max(0, (d.cert_expires_at - now).days)
        _alert(f"⚠️ گواهی دامنهٔ {d.host} تا {days} روز دیگر منقضی می‌شود — تمدید خودکار انجام نشده.\n"
               f"Store domain certificate expires in {days} day(s): {d.host}", f"tenant-domain:expiry:{d.pk}")
    if not d.dns.get("at") or now - (_dt(d.dns["at"]) or now - DNS_RECHECK) >= DNS_RECHECK:
        res = check_dns(d)
        d.dns, d.proxied = res, bool(res.get("proxied"))
    d.save()


def tick(*, only: int | None = None) -> dict:
    """Advance every live domain one step; keep the watcher's file in step. Returns counts by state."""
    now = timezone.now()
    st_all = host_status()
    qs = TenantDomain.objects.filter(state__in=LIVE).select_related("tenant").exclude(tenant__is_default=True)
    if only:
        qs = qs.filter(pk=only)
    for d in qs:
        try:
            with transaction.atomic():
                d = TenantDomain.objects.select_for_update().select_related("tenant").get(pk=d.pk)
                if d.state in (TenantDomain.PENDING_DNS, TenantDomain.VERIFIED):
                    _step_pending(d, now)
                elif d.state == TenantDomain.CERT_PENDING:
                    _step_cert(d, st_all.get(d.host) or {}, now)
                elif d.state == TenantDomain.ACTIVE:
                    _step_active(d, st_all.get(d.host) or {}, now)
        except Exception:  # noqa: BLE001 — one domain never stops the others
            log.exception("tenant domain tick failed for %s", d.host)
    write_desired()
    from django.db.models import Count

    return dict(TenantDomain.objects.values_list("state").annotate(n=Count("id")))


# ------------------------------------------------------------------ rows for the panels
def row(d: TenantDomain, st: dict | None = None, *, staff: bool = True) -> dict:
    st = st if st is not None else host_status().get(d.host) or {}
    out = {"id": d.id, "host": d.host, "www": d.include_www, "mode": d.mode, "state": d.state, "proxied": d.proxied,
           "cert_expires_at": d.cert_expires_at, "verified_at": d.verified_at, "last_check_at": d.last_check_at,
           "unhealthy_since": d.unhealthy_since, "role": d.role,
           "healthy": (d.health or {}).get("ok") if d.health else None}
    if staff:
        out.update(instructions=instructions(d), dns=d.dns or None, cert_failures=d.cert_failures, last_error=d.last_error,
                   health={k: d.health.get(k) for k in ("ok", "at", "ip", "status", "ms", "error")} if d.health else None,
                   watcher={k: st.get(k) for k in ("cert_ok", "cert_expires", "cert_error", "cert_tried_at", "challenge_ok",
                                                "challenge_error", "nginx_ok", "nginx_error", "at")} if st else None)
    return out


def rows_for(tenant_id: int, *, staff: bool = True) -> list[dict]:
    st = host_status()
    return [row(d, st.get(d.host) or {}, staff=staff)
            for d in TenantDomain.objects.filter(tenant_id=tenant_id).exclude(state=TenantDomain.REMOVED).order_by("id")]
