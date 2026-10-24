"""Tiny Cloudflare DNS client — what `configure_dns` and the domain wizard need
(token check, zones, idempotent upsert)."""
from __future__ import annotations

import requests
from django.conf import settings

API = "https://api.cloudflare.com/client/v4"


def api_base() -> str:
    """settings.CLOUDFLARE_API_BASE (the throw-away domain test points it at a mock)."""
    return (getattr(settings, "CLOUDFLARE_API_BASE", "") or API).rstrip("/")


def configured_token() -> tuple[str, str]:
    """(token, source): the token saved in the panel (encrypted) wins, .env is the fallback."""
    try:
        from apps.settings_app.models import DomainConfig

        tok = (DomainConfig.load().cloudflare_token or "").strip()
        if tok:
            return tok, "panel"
    except Exception:  # noqa: BLE001 — table missing during a migration, key problems …
        pass
    tok = (getattr(settings, "CLOUDFLARE_API_TOKEN", "") or "").strip()
    return (tok, "env") if tok else ("", "")


class CloudflareError(Exception):
    """str() = "code: message; …" as Cloudflare said it. `codes` (incl. error_chain), `status` (HTTP)
    and `network` feed apps.settings_app.domain_errors, which turns them into a fix people can follow."""

    def __init__(self, msg, *, codes=(), status=None, network=False):
        super().__init__(msg)
        self.codes, self.status, self.network = tuple(codes), status, network


class Cloudflare:
    def __init__(self, token: str):
        self._s = requests.Session()
        self._s.headers.update({"Authorization": f"Bearer {token}"})

    def _req(self, method, path, **kw):
        try:
            r = self._s.request(method, f"{api_base()}{path}", timeout=20, **kw)
        except requests.RequestException as exc:
            raise CloudflareError(f"Cloudflare API unreachable: {exc.__class__.__name__}", network=True) from exc
        try:
            body = r.json()
        except ValueError:
            raise CloudflareError(f"{method} {path}: HTTP {r.status_code}, not JSON", status=r.status_code) from None
        if not body.get("success"):
            errs = [e for e in body.get("errors") or [] if isinstance(e, dict)]
            codes = []
            for e in errs:
                for x in [e] + [c for c in e.get("error_chain") or [] if isinstance(c, dict)]:
                    try:
                        codes.append(int(x.get("code")))
                    except (TypeError, ValueError):
                        pass
            msg = "; ".join(
                f"{e.get('code')}: {e.get('message')}"
                + "".join(f" ({c.get('code')}: {c.get('message')})" for c in e.get("error_chain") or [] if isinstance(c, dict))
                for e in errs) or f"HTTP {r.status_code}"
            raise CloudflareError(msg, codes=codes, status=r.status_code)
        return body["result"]

    def verify(self) -> dict:
        return self._req("GET", "/user/tokens/verify")

    def zones(self) -> list[dict]:
        """Every zone the token can see, with the permissions Cloudflare reports for it."""
        out, page = [], 1
        while page <= 20:
            res = self._req("GET", "/zones", params={"per_page": 50, "page": page})
            out += res
            if len(res) < 50:
                break
            page += 1
        return out

    def check_zone(self, zone_id: str, zone_name: str) -> dict:
        """What the token may really do in a zone: list records (read), then create a temporary TXT
        record and delete it right away (DNS edit). → {read, dns_edit: True/False/None, error, cleanup}"""
        import secrets

        out = {"read": None, "dns_edit": None, "error": None, "cleanup": True}
        try:
            self._req("GET", f"/zones/{zone_id}/dns_records", params={"per_page": 1})
            out["read"] = True
        except CloudflareError as exc:
            out["error"] = exc
            if exc.network or (exc.status or 0) >= 500 or exc.status == 429:
                return out                                    # unknown — try again later
            out["read"] = out["dns_edit"] = False
            return out
        name = f"_caspintunel-check-{secrets.token_hex(3)}.{zone_name}"
        try:
            rec = self._req("POST", f"/zones/{zone_id}/dns_records",
                            json={"type": "TXT", "name": name, "content": "caspintunel DNS edit check - safe to delete", "ttl": 60})
        except CloudflareError as exc:
            out["error"] = exc
            if not (exc.network or (exc.status or 0) >= 500 or exc.status == 429):
                out["dns_edit"] = False
            return out
        out["dns_edit"] = True
        try:
            self._req("DELETE", f"/zones/{zone_id}/dns_records/{rec['id']}")
        except (CloudflareError, KeyError, TypeError):
            out["cleanup"] = name                              # left behind — shown so it can be deleted by hand
        return out

    def zone_id(self, name: str) -> str:
        res = self._req("GET", "/zones", params={"name": name})
        if not res:
            raise CloudflareError(f"zone {name} not found (token lacks access?)")
        return res[0]["id"]

    def find_record(self, zone: str, *, type: str, name: str):
        res = self._req("GET", f"/zones/{zone}/dns_records",
                        params={"type": type, "name": name})
        return res[0] if res else None

    def upsert(self, zone: str, *, type: str, name: str, content: str,
               proxied: bool = False, priority: int | None = None, ttl: int = 1,
               match_prefix: str | None = None) -> dict:
        payload = {"type": type, "name": name, "content": content, "ttl": ttl}
        if type in ("A", "AAAA", "CNAME"):
            payload["proxied"] = proxied
        if priority is not None:
            payload["priority"] = priority

        recs = self._req("GET", f"/zones/{zone}/dns_records", params={"type": type, "name": name})
        if type == "MX":  # only replace the record with the same exchange
            existing = next((r for r in recs if r["content"] == content), None)
        elif type == "TXT" and match_prefix:  # don't clobber unrelated TXT on the same name
            existing = next((r for r in recs if r["content"].strip('"').startswith(match_prefix)), None)
        else:
            existing = recs[0] if recs else None

        if existing:
            same = (existing.get("content") == content
                    and existing.get("proxied", False) == payload.get("proxied", False)
                    and (priority is None or existing.get("priority") == priority))
            if same:
                return {"action": "unchanged", "name": name, "type": type}
            self._req("PUT", f"/zones/{zone}/dns_records/{existing['id']}", json=payload)
            return {"action": "updated", "name": name, "type": type}

        self._req("POST", f"/zones/{zone}/dns_records", json=payload)
        return {"action": "created", "name": name, "type": type}

    # ------------------------------------------------------------------ access mode (settings_app/access.py)
    def records(self, zone: str, *, type: str, name: str) -> list[dict]:
        return self._req("GET", f"/zones/{zone}/dns_records", params={"type": type, "name": name, "per_page": 100})

    def set_a(self, zone: str, *, name: str, ips: list[str], proxied: bool, ttl: int = 1) -> list[dict]:
        """Make the A records of `name` exactly `ips` (proxied or DNS-only): existing
        ones are updated in place first, extras deleted last, so the name never
        resolves to nothing. → what changed."""
        want = list(dict.fromkeys(ips))
        have = self.records(zone, type="A", name=name)
        done, keep = [], set()
        for rec in have:                                 # already right, or proxy flag / ttl to flip
            if rec.get("content") in want and rec["content"] not in keep:
                keep.add(rec["content"])
                if rec.get("proxied", False) != proxied or (not proxied and rec.get("ttl") != ttl):
                    self._req("PATCH", f"/zones/{zone}/dns_records/{rec['id']}", json={"proxied": proxied, "ttl": ttl})
                    done.append({"name": name, "content": rec["content"], "action": "updated"})
        spare = [r for r in have if r.get("content") not in keep]
        for ip in [i for i in want if i not in keep]:    # reuse an old record (atomic swap), else create
            body = {"type": "A", "name": name, "content": ip, "proxied": proxied, "ttl": ttl}
            if spare:
                rec = spare.pop(0)
                self._req("PUT", f"/zones/{zone}/dns_records/{rec['id']}", json=body)
                done.append({"name": name, "content": ip, "action": "replaced", "was": rec.get("content")})
            else:
                self._req("POST", f"/zones/{zone}/dns_records", json=body)
                done.append({"name": name, "content": ip, "action": "created"})
        for rec in spare:
            self._req("DELETE", f"/zones/{zone}/dns_records/{rec['id']}")
            done.append({"name": name, "content": rec.get("content"), "action": "deleted"})
        return done

    def ssl_mode(self, zone: str) -> str:
        return (self._req("GET", f"/zones/{zone}/settings/ssl") or {}).get("value", "")

    def set_ssl_mode(self, zone: str, value: str) -> str:
        return (self._req("PATCH", f"/zones/{zone}/settings/ssl", json={"value": value}) or {}).get("value", "")

    def ips(self) -> dict:
        """Cloudflare's published edge ranges (public endpoint) → {ipv4_cidrs, ipv6_cidrs}."""
        return self._req("GET", "/ips")
