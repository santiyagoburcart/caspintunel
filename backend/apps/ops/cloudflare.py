"""Tiny Cloudflare DNS client — only what `configure_dns` needs (idempotent upsert)."""
from __future__ import annotations

import requests

API = "https://api.cloudflare.com/client/v4"


class CloudflareError(Exception):
    pass


class Cloudflare:
    def __init__(self, token: str):
        self._s = requests.Session()
        self._s.headers.update({"Authorization": f"Bearer {token}"})

    def _req(self, method, path, **kw):
        r = self._s.request(method, f"{API}{path}", timeout=20, **kw)
        body = r.json()
        if not body.get("success"):
            raise CloudflareError(f"{method} {path}: {body.get('errors')}")
        return body["result"]

    def verify(self) -> dict:
        return self._req("GET", "/user/tokens/verify")

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
