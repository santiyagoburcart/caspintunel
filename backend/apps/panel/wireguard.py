"""WireGuard configs (v1.55) — PasarGuard 5.6 (researched 2026-11-11, docs/wireguard.md):

* WireGuard runs on separate cores of type ``wg`` (one interface = one inbound tag, e.g. ``WG_7600``); a user gets WireGuard
  by being in a GROUP whose inbounds are WireGuard interfaces (today «wirgard» = all five). PasarGuard gives every user a key
  pair and one peer IP per WireGuard interface it can use (``proxy_settings.wireguard.peer_ips``) — so a service "has
  WireGuard" when its user has peer IPs (mirrored into ``Service.wireguard`` by every sync).
* There is no per-location endpoint: ``GET /api/user/{id}/subscription/wireguard`` returns ONE zip with one ``.conf`` per
  host of those inbounds, named ``<host remark with spaces → _>`` (e.g. ``_Ita_Testinbond.conf``). We fetch it on demand,
  split it per location and never store it. The location (country name + flag) comes from ``WireguardLocation`` by the
  remark's code («Ita», «tu», «de», «nl», «IR»); an unknown code shows as itself.
* A group counts as a WireGuard group when ALL its inbounds are WireGuard interfaces — so per-location groups created later on
  PasarGuard ("wg-de" …) are picked up by plans with no code change.
"""
from __future__ import annotations

import io
import logging
import re
import zipfile
from dataclasses import dataclass

from django.core.cache import cache

log = logging.getLogger("caspintunel")
TTL = 600


class WireguardError(Exception):
    def __init__(self, en: str, fa: str, status: int = 502):
        super().__init__(en)
        self.en, self.fa, self.status = en, fa, status

    def payload(self) -> dict:
        return {"detail": self.en, "detail_fa": self.fa}


# ------------------------------------------------------------------ groups (plan editor + validation)
def wg_tags(panel) -> set[str]:
    """Inbound tags served by WireGuard cores (type ``wg``: config.interface_name)."""
    key = f"wg:tags:{panel.pk}"
    hit = cache.get(key)
    if hit is not None:
        return set(hit)
    from .services import client_for

    raw = client_for(panel)._request("GET", "/api/cores")
    cores = raw.get("cores", raw) if isinstance(raw, dict) else raw
    tags = sorted({(c.get("config") or {}).get("interface_name") for c in cores or []
                   if str(c.get("type") or c.get("backend_type") or "").lower() == "wg"} - {None, ""})
    cache.set(key, tags, TTL)
    return set(tags)


def group_kinds(panel) -> dict[int, dict]:
    """{group id: {"name", "wireguard": only WireGuard inbounds, "has_wireguard": any, "inbounds": [...]}}"""
    key = f"wg:groups:{panel.pk}"
    hit = cache.get(key)
    if hit is not None:
        return {int(k): v for k, v in hit.items()}
    from .services import client_for

    tags = wg_tags(panel)
    out = {}
    for g in client_for(panel).list_groups():
        if not isinstance(g, dict) or g.get("id") is None:
            continue
        inb = list(g.get("inbound_tags") or [])
        wg = [t for t in inb if t in tags]
        out[int(g["id"])] = {"name": g.get("name") or f"group {g['id']}", "inbounds": inb,
                             "wireguard": bool(inb) and len(wg) == len(inb), "has_wireguard": bool(wg)}
    cache.set(key, {str(k): v for k, v in out.items()}, TTL)
    return out


def check_plan_groups(vpn_type: str, group_ids, panel) -> str | None:
    """None when the groups fit the plan type, else the Persian reason. Unknown groups (panel down) → None (not blocked)."""
    try:
        kinds = group_kinds(panel)
    except Exception as exc:  # noqa: BLE001 — the panel is down: do not block saving a plan
        log.warning("wireguard: group kinds unavailable (%s)", exc)
        return None
    ids = [int(i) for i in (group_ids or []) if int(i) in kinds]
    if not ids:
        return None if vpn_type == "sub" else "برای پلن وایرگارد گروه‌های وایرگارد را انتخاب کنید"
    wg = [i for i in ids if kinds[i]["wireguard"]]
    other = [i for i in ids if not kinds[i]["wireguard"]]
    if vpn_type == "wireguard" and (not wg or other):
        return "پلن «فقط وایرگارد» فقط گروه‌های وایرگارد می‌گیرد"
    if vpn_type == "both" and (not wg or not other):
        return "پلن «هر دو» هم گروه وایرگارد و هم گروه ساب لازم دارد"
    if vpn_type == "sub" and wg:
        return "پلن «ساب» گروه وایرگارد نمی‌گیرد — نوع را «هر دو» یا «فقط وایرگارد» کنید"
    return None


# ------------------------------------------------------------------ one user's configs (on demand, never stored)
@dataclass
class Conf:
    key: str           # stable id within the service (the location code, lower case)
    code: str          # the host remark's code («Ita», «de» …)
    name_fa: str
    name_en: str
    flag: str
    slug: str          # file name part (germany)
    sort: int
    body: bytes


def _code(member: str, username: str) -> str:
    name = member.rsplit("/", 1)[-1]
    name = name[:-5] if name.lower().endswith(".conf") else name
    if username and name.endswith(username):
        name = name[: -len(username)]
    return name.replace("_", " ").strip() or "wg"


def _locations() -> dict[str, object]:
    from .models import WireguardLocation

    return {loc.code.strip().lower(): loc for loc in WireguardLocation.objects.filter(is_active=True)}


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "wg"


def fetch_zip(service) -> bytes:
    """The user's WireGuard zip, straight from PasarGuard (admin token; the user is looked up by its username)."""
    from .exceptions import PanelError
    from .services import client_for

    c = client_for(service.panel)
    try:
        user = c._request("GET", f"/api/user/{service.panel_username}")
        resp = c._session.get(f"{c.base}/api/user/{int(user['id'])}/subscription/wireguard",
                              headers={"Authorization": f"Bearer {c._token()}"}, timeout=c.timeout)
    except (PanelError, KeyError, TypeError, ValueError) as exc:
        raise WireguardError(f"PasarGuard did not answer: {exc}"[:200], "پنل جواب نداد — کمی بعد دوباره امتحان کنید") from exc
    except Exception as exc:  # noqa: BLE001 — network
        raise WireguardError(f"PasarGuard did not answer: {exc}"[:200], "پنل جواب نداد — کمی بعد دوباره امتحان کنید") from exc
    if resp.status_code != 200 or resp.content[:2] != b"PK":
        raise WireguardError(f"no WireGuard configs (HTTP {resp.status_code})", "این سرویس کانفیگ وایرگارد ندارد", 404)
    return resp.content


def configs(service, raw: bytes | None = None) -> list[Conf]:
    raw = raw if raw is not None else fetch_zip(service)
    locs = _locations()
    out, seen = [], set()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in z.namelist():
            if not name.lower().endswith(".conf"):
                continue
            code = _code(name, service.panel_username)
            loc = locs.get(code.lower())
            key = _slug(code)
            while key in seen:
                key += "-2"
            seen.add(key)
            out.append(Conf(key=key, code=code, name_fa=loc.name_fa if loc else code, name_en=loc.name_en if loc else code,
                            flag=loc.flag if loc else "", slug=(loc.slug if loc else "") or key,
                            sort=loc.sort_order if loc else 999, body=z.read(name)))
    if not out:
        raise WireguardError("no WireGuard configs", "این سرویس کانفیگ وایرگارد ندارد", 404)
    return sorted(out, key=lambda c: (c.sort, c.name_en.lower()))


def prefix(service) -> str:
    """CT for Caspin Tunel — the initials of the CUSTOMER's store name (never our brand on a store)."""
    from apps.settings_app.branding import branding

    try:
        name = getattr(branding(), "site_name_en", "") or ""
    except Exception:  # noqa: BLE001
        name = ""
    letters = "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", name))[:4].upper()
    return letters or "WG"


def filename(service, conf: Conf) -> str:
    return f"{prefix(service)}-{service.id}-{conf.slug}.conf"[:64]


def zip_all(service, confs: list[Conf]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for c in confs:
            z.writestr(filename(service, c), c.body)
    return buf.getvalue()


def row(service, c: Conf) -> dict:
    return {"key": c.key, "code": c.code, "name_fa": c.name_fa, "name_en": c.name_en, "flag": c.flag,
            "filename": filename(service, c)}


def audit(service, *, what: str, via: str, user=None) -> None:
    from apps.common.models import write_audit

    write_audit(action="service.wireguard_download", staff=None, target=service,
                detail={"service": service.id, "user": getattr(user, "id", None) or service.user_id, "what": what, "via": via})
