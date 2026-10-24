"""Access mode (docs/access-mode.md): how visitors reach the SAME domain.

    direct      A (@, www) → this server, DNS-only
    cloudflare  A (@, www) → this server, proxied (orange cloud); SSL Full (strict)
    tunnel      A (@, www) → the Iran server's public IP(s), DNS-only; the tunnel
                forwards 443 (and 80) to this server

mail.<domain> is never touched (always DNS-only → this server).

nginx is the same in every mode — it always takes CF-Connecting-IP, but only from
Cloudflare's published ranges (refreshed daily), and optional PROXY-protocol
listeners for tunnels that send it. A switch is therefore DNS + verification:
the path is checked BEFORE DNS changes where possible (tunnel / direct: a real
TLS request to that IP, our certificate, our instance header), DNS is changed
through the Cloudflare API, the new path is checked again and DNS is put back
automatically on failure. Nothing about a tunnel is hard-coded: the Iran IP(s),
the tunnel source IPs and the PROXY ports are panel fields.

Requests that arrive from a tunnel source (and whose client IP nginx could not
resolve further) share one address, so per-IP limits are keyed by client
instead (apps.common.throttling).
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import secrets
import time

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from . import domain as D
from . import domain_errors as E
from .domain import DomainError
from .models import DomainConfig

log = logging.getLogger("caspintunel")

MODES = ("direct", "cloudflare", "tunnel")
PROXY_PORTS = ("80", "443")
GREY_TTL = 60                     # DNS-only records: one minute, so a switch (or a revert) propagates fast
SOURCES_CACHE = "access:tunnel-sources"
DETECT_KEY = "access:detect:{}"

# Cloudflare's published ranges (https://www.cloudflare.com/ips/) — used until the first refresh
BUNDLED_CF = {
    "v4": ["173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
           "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
           "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22"],
    "v6": ["2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32",
           "2a06:98c0::/29", "2c0f:f248::/32"],
}


def nginx_params_file():
    return D._dir() / ".access-nginx.json"


def _now():
    return timezone.now().isoformat()


# ------------------------------------------------------------------ validation
def clean_ips(values, *, kind: str) -> list[str]:
    """kind "iran": public IPv4 (the A record). kind "source": IPv4/IPv6 address or CIDR,
    private ranges and 127.0.0.1 allowed (reverse tunnels)."""
    if isinstance(values, str):
        values = values.replace(",", "\n").split()
    out = []
    for raw in values or []:
        v = str(raw).strip()
        if not v:
            continue
        try:
            if kind == "iran":
                ip = ipaddress.ip_address(v)
                if ip.version != 4 or not (ip.is_global or getattr(settings, "DOMAIN_ACCESS_ALLOW_PRIVATE", False)):
                    raise ValueError
                v = str(ip)
            else:
                v = str(ipaddress.ip_network(v, strict=False)) if "/" in v else str(ipaddress.ip_address(v))
        except ValueError:
            raise DomainError("ax_bad_ip", name=v, type="public IPv4 address" if kind == "iran" else "IP address or CIDR")
        if v not in out:
            out.append(v)
    if len(out) > 32:
        raise DomainError("ax_bad_ip", name=f"{len(out)} entries", type="list (at most 32)")
    return out


def cf_ranges(cfg=None) -> dict:
    cfg = cfg or DomainConfig.load()
    r = cfg.cf_ranges or {}
    return {"v4": r.get("v4") or BUNDLED_CF["v4"], "v6": r.get("v6") or BUNDLED_CF["v6"], "at": r.get("at")}


def is_cloudflare_ip(ip: str, cfg=None) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    r = cf_ranges(cfg)
    return any(a in ipaddress.ip_network(n) for n in r["v4"] + r["v6"])


# ------------------------------------------------------------------ tunnel requests (throttling)
def tunnel_networks() -> list:
    nets = cache.get(SOURCES_CACHE)
    if nets is None:
        try:
            raw = DomainConfig.load().tunnel_sources or []
        except Exception:  # noqa: BLE001 — table missing during migrate
            raw = []
        nets = [str(ipaddress.ip_network(v, strict=False)) for v in raw]
        cache.set(SOURCES_CACHE, nets, 60)
    return [ipaddress.ip_network(n) for n in nets]


def client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (xff.split(",")[0].strip() if xff else "") or request.META.get("REMOTE_ADDR", "")


def via_tunnel(request) -> bool:
    """The request came in from a tunnel source and nginx knows no better client
    address (no PROXY protocol / Cloudflare header resolved it): X-Conn-Addr (the
    TCP peer, set by nginx, never by the client) equals the client IP and is in
    the tunnel source list."""
    conn = (request.META.get("HTTP_X_CONN_ADDR") or "").strip()
    if not conn or conn != client_ip(request):
        return False
    try:
        a = ipaddress.ip_address(conn)
    except ValueError:
        return False
    return any(a in n for n in tunnel_networks())


# ------------------------------------------------------------------ path verification
def instance_id() -> str:
    """Sent by the health endpoint as X-Caspin-Instance: proves an answer came from THIS server."""
    return hashlib.sha256(("caspin-instance:" + settings.SECRET_KEY).encode()).hexdigest()[:16]


def probe(ip: str, domain: str, path: str = "/api/v1/health/", timeout: float = 10) -> dict:
    """A real HTTPS request for `domain` sent to `ip` (SNI + Host = domain): our certificate
    (unless DOMAIN_ACCESS_VERIFY_TLS is off — test stacks), status 200, our instance header."""
    import certifi
    import urllib3

    verify = getattr(settings, "DOMAIN_ACCESS_VERIFY_TLS", True)
    port = int(getattr(settings, "DOMAIN_ACCESS_PORT", 443))
    ip = (getattr(settings, "DOMAIN_ACCESS_PROBE_REWRITE", None) or {}).get(ip, ip)     # throw-away test stacks only
    started = time.monotonic()
    res = {"ip": ip, "ok": False, "status": None, "ms": None, "error": ""}
    pool = urllib3.HTTPSConnectionPool(
        ip, port=port, server_hostname=domain, assert_hostname=domain if verify else False,
        cert_reqs="CERT_REQUIRED" if verify else "CERT_NONE", ca_certs=certifi.where() if verify else None,
        timeout=urllib3.Timeout(connect=min(timeout, 6), read=timeout), retries=False)
    try:
        r = pool.request("GET", path, headers={"Host": domain, "User-Agent": "caspin-access-check"}, redirect=False)
        res.update(status=r.status, ms=int((time.monotonic() - started) * 1000))
        mine = r.headers.get("X-Caspin-Instance") == instance_id()
        if r.status == 200 and mine:
            res["ok"], res["data"] = True, r.data[:2000].decode("utf-8", "replace")
        elif not mine:
            res["error"] = f"HTTP {r.status} from something that is not this server (no X-Caspin-Instance)"
        else:
            res["error"] = f"HTTP {r.status}"
    except urllib3.exceptions.SSLError as exc:
        res["error"] = f"TLS: the certificate on {ip}:{port} is not valid for {domain} — {str(exc)[:160]}"
    except (urllib3.exceptions.ConnectTimeoutError, urllib3.exceptions.MaxRetryError, urllib3.exceptions.NewConnectionError) as exc:
        res["error"] = f"no answer on {ip}:{port} — {str(exc)[:160]}"
    except Exception as exc:  # noqa: BLE001
        res["error"] = f"{exc.__class__.__name__}: {str(exc)[:160]}"
    finally:
        pool.close()
    return res


def _probe_all(ips, domain) -> tuple[bool, list[dict]]:
    rows = [probe(ip, domain) for ip in ips]
    return bool(rows) and all(r["ok"] for r in rows), rows


# ------------------------------------------------------------------ settings
def _apply_nginx(cfg, by) -> bool:
    """Hand the host what nginx needs (Cloudflare ranges, tunnel sources, PROXY ports);
    scripts/domain.sh `access` renders + tests + reloads it. False when another host
    step is queued (tick() retries)."""
    r = cf_ranges(cfg)
    params = {"cf_v4": r["v4"], "cf_v6": r["v6"], "sources": cfg.tunnel_sources or [],
              "proxy_ports": [p for p in PROXY_PORTS if (cfg.proxy_protocol or {}).get(p)], "at": _now()}
    path = nginx_params_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(params))
    os.replace(tmp, path)
    try:
        D._write_request({"action": "access", "id": None, "domain": D.current_domain(), "requested_by": D._by(by), "at": _now()})
    except DomainError:
        return False
    st = dict(cfg.access_state or {})
    st["nginx"] = {"state": "running", "at": _now(), "message": "queued — the server applies it within a minute"}
    DomainConfig.objects.filter(pk=1).update(access_state=st)
    return True


def save_settings(*, iran_ips=None, tunnel_sources=None, proxy_protocol=None, by) -> dict:
    cfg = DomainConfig.load()
    old = (list(cfg.iran_ips or []), list(cfg.tunnel_sources or []), dict(cfg.proxy_protocol or {}))
    if iran_ips is not None:
        cfg.iran_ips = clean_ips(iran_ips, kind="iran")
    if tunnel_sources is not None:
        cfg.tunnel_sources = clean_ips(tunnel_sources, kind="source")
    if proxy_protocol is not None:
        cfg.proxy_protocol = {p: bool((proxy_protocol or {}).get(p)) for p in PROXY_PORTS}
    cfg.save()
    cache.delete(SOURCES_CACHE)
    D._audit("access_settings", by, iran_ips=cfg.iran_ips, tunnel_sources=cfg.tunnel_sources, proxy_protocol=cfg.proxy_protocol)
    out = {"nginx_queued": None, "switch": None}
    if (old[1], old[2]) != (cfg.tunnel_sources, cfg.proxy_protocol):
        out["nginx_queued"] = _apply_nginx(cfg, by)
    if old[0] != cfg.iran_ips and cfg.access_mode == "tunnel" and cfg.iran_ips:
        out["switch"] = request_switch("tunnel", by, reason="Iran IP changed")      # updates DNS (verified, reverts on failure)
    return out


# ------------------------------------------------------------------ Cloudflare ranges (daily)
def refresh_cf_ranges() -> bool:
    """Cloudflare's /ips (public). Changed → stored + nginx re-rendered. True when changed."""
    from apps.ops.cloudflare import api_base

    try:
        body = requests.get(f"{api_base()}/ips", timeout=15).json()
        res = body.get("result") or {}
        v4, v6 = sorted(res.get("ipv4_cidrs") or []), sorted(res.get("ipv6_cidrs") or [])
        for n in v4 + v6:
            ipaddress.ip_network(n)
    except (requests.RequestException, ValueError, AttributeError) as exc:
        log.warning("Cloudflare ranges not refreshed: %s", exc)
        return False
    if not v4:
        return False
    cfg = DomainConfig.load()
    cur = cfg.cf_ranges or {}
    changed = (sorted(cur.get("v4") or []), sorted(cur.get("v6") or [])) != (v4, v6)
    cfg.cf_ranges = {"v4": v4, "v6": v6, "at": _now(), "applied": cur.get("applied") if not changed else None}
    cfg.save(update_fields=["cf_ranges", "updated_at"])
    if changed or not cur.get("applied"):
        _apply_nginx(cfg, "schedule")
    return changed


# ------------------------------------------------------------------ the switch
def _names(domain: str) -> list[str]:
    host = D._read(D.state_file()) or {}
    www = host.get("www", True) if host.get("domain") == domain else True
    return [domain] + ([f"www.{domain}"] if www else [])


def _zone(cf, domain: str) -> dict:
    zones = cf.zones()
    fits = [z for z in zones if domain == z["name"] or domain.endswith("." + z["name"])]
    if not fits:
        raise DomainError("ax_no_zone", zone=domain)
    return max(fits, key=lambda z: len(z["name"]))


def _target(cfg, mode: str) -> tuple[list[str], bool]:
    if mode == "tunnel":
        return list(cfg.iran_ips or []), False
    return [D.server_ip()], mode == "cloudflare"


def request_switch(mode: str, by, *, skip_verify: bool = False, reason: str = "") -> dict:
    if mode not in MODES:
        raise DomainError("ax_mode")
    cfg = DomainConfig.load()
    st = cfg.access_state or {}
    if st.get("status") == "running":
        raise DomainError("ax_busy")
    if D.active_change():
        raise DomainError("ax_wizard")
    if mode == "tunnel":
        if not cfg.iran_ips:
            raise DomainError("ax_no_iran")
        if not cfg.tunnel_sources:
            raise DomainError("ax_no_sources")
    D._client()                                                     # a Cloudflare token is needed (DNS)
    sid = secrets.token_hex(6)
    cfg.access_state = {"id": sid, "from": cfg.access_mode, "to": mode, "status": "running", "by": D._by(by),
                        "at": _now(), "reason": reason, "skip_verify": bool(skip_verify), "steps": {},
                        "nginx": st.get("nginx"), "history": (st.get("history") or [])[:9]}
    cfg.save(update_fields=["access_state", "updated_at"])
    D._audit("access_requested", by, frm=cfg.access_mode, to=mode, skip_verify=bool(skip_verify), reason=reason)
    from .tasks import access_switch_task

    access_switch_task.delay(sid)
    return cfg.access_state


def _step(cfg, key, state, message="", **detail):
    st = cfg.access_state
    st["steps"][key] = {"state": state, "message": message, "at": _now(), **detail}
    DomainConfig.objects.filter(pk=1).update(access_state=st)


def _finish(cfg, status, message, error=None):
    st = cfg.access_state
    st.update(status=status, message=message, finished_at=_now(), **({"error": error} if error else {}))
    st["history"] = [{"from": st["from"], "to": st["to"], "status": status, "at": st["at"], "by": st.get("by"),
                      "message": message}] + (st.get("history") or [])[:9]
    fields = {"access_state": st}
    if status == "ok":
        fields["access_mode"] = st["to"]
        cfg.access_mode = st["to"]
    DomainConfig.objects.filter(pk=1).update(**fields)
    D._audit(f"access_{status}", st.get("by") or "system", frm=st["from"], to=st["to"], message=message,
             error=(error or {}).get("raw", ""))


def _wait_dns(domain, want: list[str] | None, *, cloudflare: bool, cfg) -> tuple[bool, list[str]]:
    """Public DNS (DoH) answers the target: exactly `want`, or only Cloudflare edges."""
    deadline = time.monotonic() + int(getattr(settings, "DOMAIN_ACCESS_PROPAGATION_SECONDS", 180))
    seen: list[str] = []
    while True:
        res = D.resolve(domain, "A")
        answered = [r for r in res["resolvers"] if "error" not in r and r["ips"]]
        seen = sorted({i for r in answered for i in r["ips"]})
        if answered and (all(all(is_cloudflare_ip(i, cfg) for i in r["ips"]) for r in answered) if cloudflare
                         else all(set(r["ips"]) == set(want or []) for r in answered)):
            return True, seen
        if time.monotonic() >= deadline:
            return False, seen
        time.sleep(int(getattr(settings, "DOMAIN_ACCESS_POLL_SECONDS", 5)))


def run_switch(sid: str) -> None:
    from apps.ops.cloudflare import CloudflareError

    cfg = DomainConfig.load()
    st = cfg.access_state or {}
    if st.get("id") != sid or st.get("status") != "running":
        return
    mode, domain = st["to"], D.current_domain()
    skip = st.get("skip_verify")
    cf = None
    try:
        cf = D._client()
        zone = _zone(cf, domain)
        ips, proxied = _target(cfg, mode)
        names = _names(domain)
        _step(cfg, "check", "ok", f"zone {zone['name']} · {', '.join(names)} → {', '.join(ips)}"
              + (" (proxied)" if proxied else " (DNS only)"), zone=zone["name"])
        if mode == "cloudflare":                       # Full (strict) or refuse
            ssl = cf.ssl_mode(zone["id"])
            if ssl != "strict":
                try:
                    ssl = cf.set_ssl_mode(zone["id"], "strict")
                except CloudflareError as exc:
                    raise DomainError(E.explain("ax_ssl", str(exc), status=ssl or "unknown")) from exc
            _step(cfg, "ssl", "ok", "SSL/TLS: Full (strict)")
        # 1) the new path BEFORE DNS changes: tunnel → through the Iran IP(s); direct / proxy → the origin
        #    itself (Full strict needs our certificate there; an edge can't serve us before the record is proxied)
        if not skip:
            good, rows = _probe_all(ips, domain)
            if not good:
                bad = next(r for r in rows if not r["ok"])
                raise DomainError(E.explain("ax_path", bad["error"], name=bad["ip"], seen=bad["error"]))
            _step(cfg, "preverify", "ok", f"{domain} answers through {', '.join(ips)}", probes=rows)
        # 2) DNS (root + www; mail.* never)
        before = {n: [{"content": r.get("content"), "proxied": r.get("proxied", False), "ttl": r.get("ttl", 1)}
                      for r in cf.records(zone["id"], type="A", name=n)] for n in names}
        cfg.access_state["before"] = before
        changes = []
        for n in names:
            changes += cf.set_a(zone["id"], name=n, ips=ips, proxied=proxied, ttl=1 if proxied else GREY_TTL)
        _step(cfg, "dns", "ok", f"DNS updated ({len(changes)} change(s))", changes=changes)
    except DomainError as exc:
        return _finish(cfg, "failed", exc.info["en"], exc.info)
    except CloudflareError as exc:
        info = E.cloudflare(exc, zone=domain)
        return _finish(cfg, "failed", info["en"], info)

    # 3) after DNS: public DNS + the path again; anything wrong → put DNS back
    try:
        ok, seen = _wait_dns(domain, ips, cloudflare=proxied, cfg=cfg)
        _step(cfg, "propagate", "ok" if ok else "waiting",
              f"public DNS: {', '.join(seen) or '—'}" + ("" if ok else " (not everywhere yet)"))
        if skip:
            return _finish(cfg, "ok", f"now in {mode} mode (verification skipped)")
        if proxied:
            if not ok:
                raise DomainError(E.explain("ax_edge", ", ".join(seen)))
            good, rows = _probe_all(seen[:2], domain)
        else:
            good, rows = _probe_all(ips, domain)
        if not good:
            bad = next(r for r in rows if not r["ok"])
            raise DomainError(E.explain("ax_reverted", bad["error"], seen=bad["error"]))
        _step(cfg, "verify", "ok", f"{domain} answers through the new path", probes=rows)
        return _finish(cfg, "ok", f"now in {mode} mode")
    except DomainError as exc:
        _revert(cfg, cf, domain)
        return _finish(cfg, "reverted", exc.info["en"], exc.info)


def _revert(cfg, cf, domain):
    before = (cfg.access_state or {}).get("before") or {}
    try:
        zone = _zone(cf, domain)
        for name, recs in before.items():
            if recs:
                cf.set_a(zone["id"], name=name, ips=[r["content"] for r in recs], proxied=bool(recs[0]["proxied"]),
                         ttl=recs[0]["ttl"] or 1)
        _step(cfg, "revert", "ok", "DNS put back to the previous records")
    except Exception as exc:  # noqa: BLE001 — must report, never raise
        log.exception("access revert failed")
        _step(cfg, "revert", "failed", f"could not restore DNS: {exc}")


# ------------------------------------------------------------------ auto-detect the tunnel source
def detect(by) -> dict:
    """Send a test request through each Iran IP to the probe endpoint and report the
    TCP peer address this server saw (what to put in "tunnel source IPs")."""
    cfg = DomainConfig.load()
    if not cfg.iran_ips:
        raise DomainError("ax_no_iran")
    domain = D.current_domain()
    nonce = secrets.token_urlsafe(12)
    cache.set(DETECT_KEY.format(nonce), [], 600)
    rows = []
    for ip in cfg.iran_ips:
        r = probe(ip, domain, path=f"/api/v1/domain-probe/{nonce}/")
        seen = cache.get(DETECT_KEY.format(nonce)) or []
        rows.append({"ip": ip, "ok": r["ok"] and bool(seen), "error": r["error"], "seen": seen[-1] if seen else None})
    found = sorted({x["seen"]["conn"] for x in rows if x["seen"]})
    D._audit("access_detect", by, found=found, iran_ips=cfg.iran_ips)
    out = {"found": found, "rows": rows, "nonce": nonce,
           "command": f"curl -sk --resolve {domain}:443:127.0.0.1 https://{domain}/api/v1/domain-probe/{nonce}/"}
    if not found:
        out["error"] = E.explain("ax_detect", "; ".join(f"{x['ip']}: {x['error'] or 'no request arrived'}" for x in rows),
                                 name=", ".join(cfg.iran_ips))
    return out


def record_probe(nonce: str, request) -> dict | None:
    key = DETECT_KEY.format(nonce)
    seen = cache.get(key)
    if seen is None:
        return None
    row = {"conn": (request.META.get("HTTP_X_CONN_ADDR") or client_ip(request)).strip(),
           "client": client_ip(request), "at": _now()}
    cache.set(key, (seen + [row])[-10:], 600)
    return row


# ------------------------------------------------------------------ host results + API state
def request_dns01(by) -> dict:
    """Certificates via DNS-01 with the Cloudflare token (works in every mode): the host writes
    the root-only certbot credentials and switches the live certificate's renewal."""
    D._client()
    D._write_request({"action": "dns01", "id": None, "domain": D.current_domain(), "requested_by": D._by(by), "at": _now()})
    cfg = DomainConfig.load()
    cfg.dns01 = {**(cfg.dns01 or {}), "state": "running", "at": _now(),
                 "message": "queued — the server switches certificate renewal within a minute"}
    cfg.save(update_fields=["dns01", "updated_at"])
    D._audit("dns01_requested", by)
    return cfg.dns01


def sync_host() -> None:
    """Fold the host's `access` (nginx render) / `dns01` result into the config."""
    stt = D._read(D.status_file()) or {}
    cfg = DomainConfig.load()
    if stt.get("action") == "dns01":
        if (cfg.dns01 or {}).get("host_at") != stt.get("at"):
            DomainConfig.objects.filter(pk=1).update(dns01={
                "state": "ok" if stt.get("ok") else "failed", "enabled": bool(stt.get("ok")) or (cfg.dns01 or {}).get("enabled", False),
                "message": stt.get("message", ""), "at": stt.get("at"), "host_at": stt.get("at"),
                **({} if stt.get("ok") else {"error": E.host("cert", stt.get("message", ""), D.current_domain())})})
        return
    if stt.get("action") != "access":
        return
    st = dict(cfg.access_state or {})
    if (st.get("nginx") or {}).get("host_at") == stt.get("at"):
        return
    st["nginx"] = {"state": "ok" if stt.get("ok") else "failed", "message": stt.get("message", ""), "at": stt.get("at"),
                   "host_at": stt.get("at"),
                   **({} if stt.get("ok") else {"error": E.host("access", stt.get("message", ""), D.current_domain())})}
    fields = {"access_state": st}
    if stt.get("ok") and cfg.cf_ranges:
        fields["cf_ranges"] = {**cfg.cf_ranges, "applied": stt.get("at")}
    DomainConfig.objects.filter(pk=1).update(**fields)


def state(cfg=None) -> dict:
    cfg = cfg or DomainConfig.load()
    r = cf_ranges(cfg)
    return {
        "mode": cfg.access_mode, "iran_ips": cfg.iran_ips or [], "tunnel_sources": cfg.tunnel_sources or [],
        "proxy_protocol": {p: bool((cfg.proxy_protocol or {}).get(p)) for p in PROXY_PORTS},
        "proxy_listen": {"80": int(getattr(settings, "ACCESS_PROXY_HTTP_PORT", 8880)),
                         "443": int(getattr(settings, "ACCESS_PROXY_HTTPS_PORT", 8843))},
        "cf_ranges": {"count": len(r["v4"]) + len(r["v6"]), "at": r.get("at"), "applied": (cfg.cf_ranges or {}).get("applied")},
        "switch": cfg.access_state or None, "dns01": cfg.dns01 or None, "server_ip": D.server_ip(),
    }
