"""Domain change wizard + Cloudflare token (docs/domain.md).

Django does what needs no docker: the Cloudflare token (encrypted, write-only),
DNS records through the Cloudflare API (or the exact records for manual DNS),
the check that the names resolve to this server (public DNS-over-HTTPS, what
Let's Encrypt sees), the wizard state, audit log and the Telegram menu button.

Everything that touches certbot, nginx, .env or containers runs on the HOST —
the web container never gets docker access. Same pattern as Paths: Django
writes backups/.domain-request.json, the host watcher
(scripts/domain.sh apply-request, cron every minute) does the work, validates,
rolls back on failure and writes backups/.domain-status.json (+ the public
backups/.domain-state.json), which `sync()` folds back into the wizard.
"""
from __future__ import annotations

import json
import os
import re
from datetime import timedelta
from pathlib import Path

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.models import write_audit

from . import domain_errors as E
from .models import DomainChange, DomainConfig, SiteConfig

S = DomainChange.Status
ACTIVE = (S.DRAFT, S.APPLYING, S.TRANSITION)
STEPS = ("domain", "dns", "tls", "mail", "apply", "links", "transition")
CHECKLIST = ("shortcut", "sms_app", "botfather", "ptr", "notify")
DNS_TYPES = {"A": 1, "MX": 15, "TXT": 16}
DNS_EDIT = "#dns_records:edit"
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_DOMAIN_RE = re.compile(rf"^(?:{_LABEL}\.)+[a-z][a-z0-9-]{{0,61}}[a-z0-9]$")


class DomainError(Exception):
    """A refused wizard action. Built from a domain_errors key (+ context) or a ready
    explanation dict: str() is the English text, `.info` = {key, en, fa, raw} for the page."""

    def __init__(self, what, **ctx):
        info = what if isinstance(what, dict) else E.explain(what, **ctx) if what in E.MSG else None
        super().__init__(info["en"] if info else str(what))
        self.info = info or {"key": "other", "en": str(what), "fa": str(what), "raw": ""}


# ------------------------------------------------------------------ files shared with the host
def _dir() -> Path:
    return Path(os.path.dirname(getattr(settings, "UPDATE_SENTINEL_PATH", "/app/backups/.update-requested")))


def request_file() -> Path:
    return _dir() / ".domain-request.json"


def status_file() -> Path:
    return _dir() / ".domain-status.json"


def state_file() -> Path:
    return _dir() / ".domain-state.json"


def dkim_file() -> Path:
    return _dir() / ".domain-dkim.json"


def _read(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _write_request(data: dict) -> dict:
    path = request_file()
    if path.exists():
        raise DomainError("queued")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)
    return data


# ------------------------------------------------------------------ basics
def current_domain() -> str:
    host = _read(state_file()) or {}
    return (host.get("domain") or getattr(settings, "DOMAIN", "") or "").strip().lower()


def server_ip() -> str:
    from apps.adminpanel.views.monitoring import _public_ip

    return (_public_ip() or "").strip()


def normalize(raw: str) -> str:
    d = (raw or "").strip().lower()
    d = re.sub(r"^[a-z]+://", "", d).split("/")[0].split(":")[0].rstrip(".")
    if d.startswith("www."):
        d = d[4:]
    try:
        d = d.encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    return d


def validate_domain(d: str) -> str | None:
    """→ a domain_errors key, or None"""
    if re.fullmatch(r"[0-9.]+", d or ""):
        return "ip_domain"
    if not d or len(d) > 253 or not _DOMAIN_RE.match(d):
        return "bad_domain"
    if d == current_domain():
        return "same_domain"
    return None


def hosts(change) -> list[str]:
    return [change.new_domain] + ([f"www.{change.new_domain}"] if change.include_www else [])


def records(change) -> list[dict]:
    """The A records the new domain needs. mail is optional (only for the mail server / its cert)."""
    ip = change.server_ip or server_ip()
    out = [{"type": "A", "name": change.new_domain, "content": ip, "proxied": False, "required": True}]
    if change.include_www:
        out.append({"type": "A", "name": f"www.{change.new_domain}", "content": ip, "proxied": False, "required": True})
    out.append({"type": "A", "name": f"mail.{change.new_domain}", "content": ip, "proxied": False, "required": True})
    return out


def dkim_of(change) -> dict | None:
    d = ((change.steps or {}).get("tls") or {}).get("detail", {}).get("dkim")
    return d if d and d.get("txt") else None


def mail_records(change) -> list[dict]:
    """Mail moves with the domain: MX, SPF (this IP), DMARC (p=none) and the DKIM key the mail server made."""
    d, ip = change.new_domain, change.server_ip or server_ip()
    out = [{"type": "MX", "name": d, "content": f"mail.{d}", "priority": 10, "match": None},
           {"type": "TXT", "name": d, "content": f"v=spf1 ip4:{ip} mx ~all", "match": "v=spf1"},
           {"type": "TXT", "name": f"_dmarc.{d}", "content": "v=DMARC1; p=none; adkim=r; aspf=r", "match": "v=DMARC1"}]
    dk = dkim_of(change)
    out.append({"type": "TXT", "name": f"{(dk or {}).get('selector', 'mail')}._domainkey.{d}",
                "content": dk["txt"] if dk else "", "match": "v=DKIM1"})
    return out


def _now():
    return timezone.now().isoformat()


def set_step(change, key, state, message="", **detail):
    change.steps = {**(change.steps or {}), key: {"state": state, "message": message, "at": _now(), **({"detail": detail} if detail else {})}}


def _audit(action, by, change=None, **detail):
    staff = by if hasattr(by, "username") else None
    label = by if isinstance(by, str) else None
    log = write_audit(action=f"domain.{action}", staff=staff, target=change, detail=detail)
    if label and not staff:
        log.staff_label = label
        log.save(update_fields=["staff_label"])
    return log


def _by(by) -> str:
    return getattr(by, "username", None) or str(by or "")


# ------------------------------------------------------------------ Cloudflare token
def save_token(token: str, by) -> DomainConfig:
    cfg = DomainConfig.load()
    cfg.cloudflare_token = (token or "").strip()
    cfg.token_updated_at = timezone.now()
    cfg.token_updated_by = _by(by)
    cfg.last_test = {}
    cfg.save()
    _audit("token_cleared" if not cfg.cloudflare_token else "token_saved", by)
    return cfg


def test_token(token: str | None, by=None) -> dict:
    """Verify a token (the one typed in, else the saved / .env one): status,
    zones it can see and whether it may edit DNS there. Never returns the token."""
    from apps.ops.cloudflare import Cloudflare, CloudflareError, configured_token

    source = "typed"
    if not token:
        token, source = configured_token()
    res = {"ok": False, "at": _now(), "source": source, "status": "", "zones": [], "permissions": [], "error": "", "error_fa": "", "explain": None}

    def fail(info):
        res["error"], res["error_fa"], res["explain"] = info["en"], info["fa"], info

    if not token:
        fail(E.explain("cf_no_token"))
    else:
        cf, ip = Cloudflare(token), server_ip()
        try:
            v = cf.verify()
            res["status"] = v.get("status", "")
            res["expires_on"] = v.get("expires_on")
            if res["status"] != "active":
                raise DomainError("cf_inactive", status=res["status"] or "unknown")
            perms = set()
            for i, z in enumerate(cf.zones()):
                zp = z.get("permissions")
                perms.update(zp or [])
                row = {"id": z.get("id"), "name": z.get("name"), "status": z.get("status"),
                       "reported": (DNS_EDIT in zp) if isinstance(zp, list) else None,
                       "read": None, "dns_edit": None, "error": None}
                if i < ZONE_CHECK_MAX:          # the real thing: write + delete a temporary TXT record
                    row.update(zone_check(cf, row["id"], row["name"], ip))
                else:
                    row["dns_edit"] = row["reported"]
                res["zones"].append(row)
            res["permissions"] = sorted(perms)
            if not res["zones"]:
                fail(E.explain("cf_no_zones"))
            elif not any(z["dns_edit"] for z in res["zones"]):
                bad = next((z["error"] for z in res["zones"] if z["error"]), None)
                fail(bad if bad and (bad["key"] != "cf_perm" or len(res["zones"]) == 1)
                     else E.explain("cf_no_edit", (bad or {}).get("raw", "")))
            else:
                res["ok"] = True
                if any(z["dns_edit"] is None for z in res["zones"]):
                    res["note"] = "some zones could not be checked — DNS edit is confirmed on the first record write"
        except CloudflareError as exc:
            fail(E.cloudflare(exc, ip=ip))
        except DomainError as exc:
            fail(exc.info)
    if source != "typed":
        cfg = DomainConfig.load()
        cfg.last_test = res
        cfg.save(update_fields=["last_test", "updated_at"])
    if by is not None:
        _audit("token_tested", by, ok=res["ok"], source=source, error=res["error"], zones=[z["name"] for z in res["zones"]])
    return res


def _client():
    from apps.ops.cloudflare import Cloudflare, configured_token

    token, _ = configured_token()
    if not token:
        raise DomainError("cf_no_token")
    return Cloudflare(token)


ZONE_CHECK_MAX = 25


def zone_check(cf, zone_id: str, zone_name: str, ip: str = "") -> dict:
    """{read, dns_edit, error (explained), cleanup} — see Cloudflare.check_zone."""
    r = cf.check_zone(zone_id, zone_name)
    err = E.cloudflare(r["error"], zone=zone_name, ip=ip or server_ip()) if r["error"] else None
    if err and r["dns_edit"] is False and r["read"] is not False and err["key"] in ("cf_other", "cf_record", "cf_exists"):
        err = E.explain("cf_perm", err["raw"], zone=zone_name)   # refused write = no DNS edit, whatever the code
    return {"read": r["read"], "dns_edit": r["dns_edit"], "error": err,
            **({"leftover": r["cleanup"]} if r["cleanup"] is not True else {})}


# ------------------------------------------------------------------ DNS check (public DoH)
def resolve(name: str, rtype: str = "A") -> dict:
    out = []
    for url in getattr(settings, "DOMAIN_DOH_URLS", []):
        try:
            r = requests.get(url, params={"name": name, "type": rtype}, headers={"accept": "application/dns-json"}, timeout=6)
            body = r.json()
            ips = [a.get("data") for a in body.get("Answer") or [] if a.get("type") == DNS_TYPES[rtype]]
            out.append({"resolver": url.split("/")[2], "ips": ips})
        except (requests.RequestException, ValueError) as exc:
            out.append({"resolver": url.split("/")[2], "ips": [], "error": exc.__class__.__name__})
    return {"name": name, "resolvers": out}


def dns_check(change, by=None) -> DomainChange:
    ip = change.server_ip
    rows, ok = [], True
    for rec in records(change):
        res = resolve(rec["name"])
        answered = [r for r in res["resolvers"] if "error" not in r]
        good = bool(answered) and all(ip in r["ips"] for r in answered)
        seen = sorted({i for r in answered for i in r["ips"]})
        rows.append({"name": rec["name"], "required": rec["required"], "ok": good, "seen": seen,
                     "errors": [r["resolver"] for r in res["resolvers"] if "error" in r],
                     "why": None if good else E.dns_host(rec["name"], ip, res["resolvers"])})
        ok = ok and (good or not rec["required"])
    keep = {k: v for k, v in ((change.steps.get("dns") or {}).get("detail") or {}).items() if k in ("zone_check", "records")}
    if ok:
        set_step(change, "dns", "ok", f"resolves to {ip}", hosts=rows, **keep)
    else:
        bad = [r for r in rows if r["required"] and not r["ok"]]
        set_step(change, "dns", "waiting", f"not yet pointing at {ip}: {', '.join(r['name'] for r in bad)}",
                 hosts=rows, error=bad[0]["why"], **keep)
    change.save()
    if by is not None:
        _audit("dns_checked", by, change, ok=ok, hosts=rows)
    return change


def _txt(v: str) -> str:
    """DoH TXT data → plain text ("a" "b" → ab)."""
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', v or "")
    return "".join(parts) if parts else (v or "")


def mail_check(change, by=None) -> DomainChange:
    """MX / SPF / DMARC / DKIM of the new domain as public DNS answers them."""
    rows, ok = [], True
    for rec in mail_records(change):
        res = resolve(rec["name"], rec["type"])
        answered = [r for r in res["resolvers"] if "error" not in r]
        if rec["type"] == "MX":
            vals = [list(r["ips"]) for r in answered]
            seen = sorted({v.split()[-1].rstrip(".") for r in answered for v in r["ips"]})
            good = bool(answered) and all(any(v.split()[-1].rstrip(".") == rec["content"] for v in r["ips"]) for r in answered)
        else:
            vals = [[_txt(v) for v in r["ips"]] for r in answered]
            seen = sorted({v[:60] for vs in vals for v in vs if v.startswith(rec["match"])})
            want = rec["content"].replace(" ", "")
            good = bool(rec["content"]) and bool(answered) and all(any(v.replace(" ", "") == want for v in vs) for vs in vals)
            if good and rec["match"] == "v=spf1" and any(sum(v.startswith("v=spf1") for v in vs) > 1 for vs in vals):
                good = False                                    # ours is there, but a second SPF breaks SPF
        rows.append({"name": rec["name"], "type": rec["type"], "ok": good, "seen": seen,
                     "why": None if good else E.mail_record(rec, vals, res["resolvers"])})
        ok = ok and good
    if ok:
        set_step(change, "mail", "ok", "MX, SPF, DKIM and DMARC published", hosts=rows)
    else:
        bad = [r for r in rows if not r["ok"]]
        set_step(change, "mail", "waiting", f"not yet in public DNS: {', '.join(r['type'] + ' ' + r['name'] for r in bad)}",
                 hosts=rows, error=bad[0]["why"])
    change.save()
    if by is not None:
        _audit("mail_checked", by, change, ok=ok, records=rows)
    return change


def mail_publish(change, by) -> DomainChange:
    """Cloudflare: write MX / SPF / DMARC / DKIM (other TXT records on the same names are left alone). Manual: check."""
    _need(change)
    if not dkim_of(change):
        raise DomainError("mail_no_dkim")
    if change.mode == "manual":
        return mail_check(change, by)
    from apps.ops.cloudflare import CloudflareError

    cf, done = _client(), []
    for rec in mail_records(change):
        try:
            res = cf.upsert(change.zone_id, type=rec["type"], name=rec["name"], content=rec["content"],
                            priority=rec.get("priority"), match_prefix=rec["match"])
            done.append({"name": rec["name"], "type": rec["type"], "action": res["action"]})
        except CloudflareError as exc:
            msg = f"{rec['type']} {rec['name']}: {exc}"
            info = E.cloudflare(exc, zone=change.zone_name, name=rec["name"], ip=change.server_ip)
            set_step(change, "mail", "failed", msg, records=done, error=info)
            change.save()
            _audit("mail_failed", by, change, error=msg, records=done)
            raise DomainError(info) from exc
    _audit("mail_records", by, change, zone=change.zone_name, records=done)
    return mail_check(change, by)


# ------------------------------------------------------------------ wizard
def active_change():
    return DomainChange.objects.filter(status__in=ACTIVE).first()


def start(*, domain, include_www=True, mode="cloudflare", zone_id="", by) -> DomainChange:
    d = normalize(domain)
    err = validate_domain(d)
    if err:
        raise DomainError(err, domain=d or (domain or "").strip())
    if active_change():
        raise DomainError("busy_change")
    if mode not in ("cloudflare", "manual"):
        raise DomainError("bad_mode")
    ip = server_ip()
    if not ip:
        raise DomainError("no_ip")
    zone_name = ""
    if mode == "cloudflare":
        from apps.ops.cloudflare import CloudflareError

        try:
            zones = _client().zones()
        except CloudflareError as exc:
            raise DomainError(E.cloudflare(exc, zone=d, ip=ip)) from exc
        fits = [z for z in zones if d == z["name"] or d.endswith("." + z["name"])]
        zone = next((z for z in fits if z["id"] == zone_id), None) if zone_id else (max(fits, key=lambda z: len(z["name"])) if fits else None)
        if not zone:
            raise DomainError(E.explain("cf_zone", f"{d}: not among the token's zones ({', '.join(z['name'] for z in zones) or 'none'})", zone=d))
        zone_id, zone_name = zone["id"], zone["name"]
    change = DomainChange(old_domain=current_domain(), new_domain=d, include_www=bool(include_www), mode=mode,
                          zone_id=zone_id if mode == "cloudflare" else "", zone_name=zone_name, server_ip=ip,
                          transition_days=DomainConfig.load().transition_days, created_by=_by(by))
    set_step(change, "domain", "ok", f"{change.old_domain} → {d}")
    if mode == "manual":
        set_step(change, "dns", "waiting", "add the records below at your DNS provider, then check")
    else:
        set_step(change, "dns", "pending")
    change.save()
    _audit("started", by, change, old=change.old_domain, new=d, www=change.include_www, mode=mode, zone=zone_name)
    return change


def _need(change, status=(S.DRAFT,)):
    if change.status not in status:
        raise DomainError("bad_state", status=change.get_status_display())


def dns_apply(change, by) -> DomainChange:
    """Cloudflare: create/update the A records (DNS-only). Manual: nothing to call."""
    _need(change)
    if change.mode == "manual":
        set_step(change, "dns", "waiting", "add the records below at your DNS provider, then check")
        change.save()
        _audit("dns_manual", by, change, records=records(change))
        return change
    from apps.ops.cloudflare import CloudflareError

    cf, done = _client(), []
    # before writing anything: may this token really edit DNS in the chosen zone? (temporary TXT, deleted again)
    chk = zone_check(cf, change.zone_id, change.zone_name, change.server_ip)
    if not chk["dns_edit"]:
        info = chk["error"] or E.explain("cf_perm", zone=change.zone_name)
        set_step(change, "dns", "failed", f"{change.zone_name}: {info['raw'] or info['en']}", zone_check=chk, error=info)
        change.save()
        _audit("dns_failed", by, change, error=info["raw"] or info["key"], zone_check={k: v for k, v in chk.items() if k != "error"})
        raise DomainError(info)
    for rec in records(change):
        try:
            res = cf.upsert(change.zone_id, type="A", name=rec["name"], content=rec["content"], proxied=False)
            done.append({"name": rec["name"], "action": res["action"]})
        except CloudflareError as exc:
            msg = f"{rec['name']}: {exc}"
            info = E.cloudflare(exc, zone=change.zone_name, name=rec["name"], ip=change.server_ip)
            set_step(change, "dns", "failed", msg, records=done, zone_check=chk, error=info)
            change.save()
            _audit("dns_failed", by, change, error=msg, records=done)
            raise DomainError(info) from exc
    set_step(change, "dns", "waiting", "records saved in Cloudflare — waiting for them to resolve", records=done, zone_check=chk)
    change.save()
    _audit("dns_records", by, change, zone=change.zone_name, records=done)
    return dns_check(change)


def request_tls(change, by) -> DomainChange:
    _need(change)
    if (change.steps.get("dns") or {}).get("state") != "ok":
        raise DomainError("need_dns")
    _write_request({"action": "cert", "id": change.id, "domain": change.new_domain, "www": change.include_www,
                    "mail": True, "requested_by": _by(by), "at": _now()})
    set_step(change, "tls", "running", "queued — the server requests the certificate within a minute")
    change.save()
    _audit("tls_requested", by, change, domain=change.new_domain)
    return change


def request_apply(change, by) -> DomainChange:
    _need(change)
    if (change.steps.get("tls") or {}).get("state") != "ok":
        raise DomainError("need_tls")
    if (change.steps.get("mail") or {}).get("state") != "ok":
        raise DomainError("need_mail")
    _write_request({"action": "apply", "id": change.id, "domain": change.new_domain, "www": change.include_www, "mail": True,
                    "old_domain": change.old_domain, "transition_days": change.transition_days,
                    "zone": change.zone_name or change.new_domain, "requested_by": _by(by), "at": _now()})
    change.status = S.APPLYING
    set_step(change, "apply", "running", "queued — the server switches within a minute")
    change.save()
    _audit("apply_requested", by, change, old=change.old_domain, new=change.new_domain, transition_days=change.transition_days)
    return change


def request_retire(change, by) -> DomainChange:
    _need(change, (S.TRANSITION,))
    _write_request({"action": "retire", "id": change.id, "domain": change.new_domain, "old_domain": change.old_domain,
                    "requested_by": _by(by), "at": _now()})
    set_step(change, "transition", "running", f"queued — removing {change.old_domain}")
    change.save()
    _audit("retire_requested", by, change, old=change.old_domain)
    return change


def rollback_target():
    """The last change that moved the site (live now) → back to its old domain."""
    return DomainChange.objects.filter(status__in=(S.TRANSITION, S.DONE)).first()


def request_rollback(by) -> DomainChange:
    change = rollback_target()
    if not change or change.new_domain != current_domain():
        raise DomainError("nothing_rb")
    _write_request({"action": "rollback", "id": change.id, "domain": change.old_domain, "from": change.new_domain,
                    "www": True, "requested_by": _by(by), "at": _now()})
    set_step(change, "rollback", "running", f"queued — back to {change.old_domain}")
    change.save()
    _audit("rollback_requested", by, change, to=change.old_domain, frm=change.new_domain)
    return change


def cancel(change, by) -> DomainChange:
    _need(change)
    change.status = S.CANCELLED
    change.finished_at = timezone.now()
    change.save()
    _audit("cancelled", by, change)
    return change


def set_checklist(change, key, done, by) -> DomainChange:
    if key not in CHECKLIST:
        raise DomainError("bad_checklist")
    change.checklist = {**(change.checklist or {}), key: bool(done)}
    change.save(update_fields=["checklist", "updated_at"])
    _audit("checklist", by, change, item=key, done=bool(done))
    return change


# ------------------------------------------------------------------ after the host switched
def _menu_button(domain: str, old: str) -> tuple[str, str]:
    """Point the sales bot's Mini App menu button at the domain. → (state, message)"""
    from apps.telegram.client import TelegramError
    from apps.telegram.config import sales_client

    url = getattr(settings, "MINIAPP_URL", "") or ""
    url = url.replace(old, domain) if old and old in url else (url if domain in url else f"https://{domain}/")
    client = sales_client()
    if client is None:
        return "skipped", "sales bot has no token — nothing to update"
    try:
        client.set_chat_menu_button(text="🌐 اپ", url=url)
    except (TelegramError, requests.RequestException) as exc:
        return "failed", f"Telegram: {exc}"
    return "ok", f"menu button → {url}"


def _relink(change, domain: str, old: str, by) -> None:
    """site URL in settings (portal / renew / ticket / bot / shortcut links) + Telegram menu button."""
    sc = SiteConfig.load()
    parts = []
    if (sc.site_domain or "").strip().strip("/").lower() in ("", old):
        sc.site_domain = domain
        sc.save(update_fields=["site_domain", "updated_at"])
        parts.append(f"site URL → https://{domain}")
    else:
        parts.append(f"site URL left as {sc.site_domain} (set by hand)")
    from .models import EmailSettings

    es = EmailSettings.load()
    if old and (es.from_email or "").lower().endswith("@" + old):
        es.from_email = es.from_email[: -len(old)] + domain
        es.save(update_fields=["from_email", "updated_at"])
        parts.append(f"sender → {es.from_email}")
    state, msg = _menu_button(domain, old)
    parts.append(msg)
    set_step(change, "links", "ok" if state != "failed" else "failed", " · ".join(parts), telegram=state)
    _audit("links_updated", by, change, site_domain=sc.site_domain, telegram=state, message=msg)


def sync() -> DomainChange | None:
    """Fold the host's last result into the wizard (once per result)."""
    st = _read(status_file())
    if not st or not st.get("id"):
        return None
    with transaction.atomic():
        change = DomainChange.objects.select_for_update().filter(pk=st["id"]).first()
        if not change or (change.steps.get("_host") or {}).get("at") == st.get("at"):
            return change
        ok, msg, action = bool(st.get("ok")), st.get("message", ""), st.get("action")
        change.steps = {**change.steps, "_host": {"at": st.get("at"), "action": action}}
        who = f"host ({st.get('requested_by') or '?'})"
        if action == "cert":
            dk = _read(dkim_file()) if ok else None
            dk = dk if dk and dk.get("domain") == change.new_domain else None
            set_step(change, "tls", "ok" if ok else "failed", msg,
                     **({"expires": st["expires"]} if st.get("expires") else {}), **({"dkim": dk} if dk else {}),
                     **({} if ok else {"error": E.host("cert", msg, change.new_domain, change.server_ip)}))
            if ok and change.status == S.DRAFT:
                change.save()
                try:                      # publish the mail records right away (Cloudflare) / check them (manual)
                    mail_publish(change, f"host ({st.get('requested_by') or '?'})")
                except DomainError:
                    pass
                change.refresh_from_db()
                change.steps = {**change.steps, "_host": {"at": st.get("at"), "action": action}}
        elif action == "apply":
            if ok:
                now = timezone.now()
                change.applied_at = now
                set_step(change, "apply", "ok", msg)
                _relink(change, change.new_domain, change.old_domain, who)
                DomainConfig.objects.filter(pk=1).update(access_mode="direct")   # the wizard's records are DNS-only → here
                if change.transition_days:
                    change.status = S.TRANSITION
                    change.old_until = now + timedelta(days=change.transition_days)
                    set_step(change, "transition", "running", f"{change.old_domain} redirects (301) until {change.old_until:%Y-%m-%d}")
                else:
                    change.status, change.finished_at = S.DONE, now
                    set_step(change, "transition", "ok", f"{change.old_domain} removed (no transition period)")
            else:
                change.status = S.DRAFT       # the host restored everything — fix and retry, or cancel
                set_step(change, "apply", "failed", msg, error=E.host("apply", msg, change.new_domain, change.server_ip))
        elif action == "retire":
            if ok:
                change.status, change.finished_at = S.DONE, timezone.now()
                set_step(change, "transition", "ok", msg)
            else:
                set_step(change, "transition", "failed", msg, error=E.host("retire", msg, change.new_domain, change.server_ip))
        elif action == "rollback":
            if ok:
                change.status, change.finished_at = S.ROLLED_BACK, timezone.now()
                set_step(change, "rollback", "ok", msg)
                _relink(change, change.old_domain, change.new_domain, who)
            else:
                set_step(change, "rollback", "failed", msg, error=E.host("rollback", msg, change.old_domain, change.server_ip))
        change.save()
        _audit(f"host_{action}_{'ok' if ok else 'failed'}", who, change, message=msg)
    return change


def tick() -> None:
    """beat: pick up host results; when the transition period is over, remove the old domain."""
    sync()
    change = DomainChange.objects.filter(status=S.TRANSITION, old_until__lte=timezone.now()).first()
    if change and not request_file().exists() and (change.steps.get("transition") or {}).get("state") != "failed":
        try:
            request_retire(change, "schedule")
        except DomainError:
            pass


# ------------------------------------------------------------------ API state
def serialize(change) -> dict | None:
    if not change:
        return None
    return {
        "id": change.id, "old_domain": change.old_domain, "new_domain": change.new_domain, "include_www": change.include_www,
        "mode": change.mode, "zone_id": change.zone_id, "zone_name": change.zone_name, "server_ip": change.server_ip,
        "status": change.status, "steps": {k: v for k, v in (change.steps or {}).items() if not k.startswith("_")},
        "checklist": change.checklist or {}, "transition_days": change.transition_days,
        "old_until": change.old_until, "created_by": change.created_by, "created_at": change.created_at,
        "applied_at": change.applied_at, "finished_at": change.finished_at, "records": records(change),
        "mail_records": [{k: v for k, v in r.items() if k != "match"} for r in mail_records(change)],
    }


def state() -> dict:
    from apps.ops.cloudflare import configured_token

    sync()
    cfg = DomainConfig.load()
    _tok, source = configured_token()
    change = active_change() or DomainChange.objects.first()
    rb = rollback_target()
    cur = current_domain()
    pending = _read(request_file())
    last = _read(status_file())
    if last and not last.get("ok"):
        last["explain"] = E.host(last.get("action") or "", last.get("message") or "", last.get("domain") or cur, server_ip())
    from . import access

    access.sync_host()
    return {
        "access": access.state(),
        "current": {"domain": cur, "server_ip": server_ip(), "site_domain": SiteConfig.load().site_domain,
                    "public_base_url": getattr(settings, "PUBLIC_BASE_URL", ""), "host": _read(state_file())},
        "cloudflare": {"token_set": bool(cfg.cloudflare_token), "source": source, "updated_at": cfg.token_updated_at,
                       "updated_by": cfg.token_updated_by, "last_test": cfg.last_test or None},
        "transition_days": cfg.transition_days,
        "change": serialize(change),
        "history": [serialize(c) for c in DomainChange.objects.all()[:10]],
        "pending": {k: pending.get(k) for k in ("action", "id", "domain", "at", "requested_by")} if pending else None,
        "last": last,
        "rollback": {"to": rb.old_domain, "from": rb.new_domain, "id": rb.id} if rb and rb.new_domain == cur else None,
        "checklist_keys": list(CHECKLIST),
    }
