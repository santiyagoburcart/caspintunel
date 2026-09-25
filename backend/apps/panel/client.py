"""
HTTP client for the Pasargad panel (PasarGuard API, Marzban lineage).

Only the panel's REST API is called from here — none of its (AGPL) code is
imported or vendored. Endpoints follow the PasarGuard OpenAPI (`/openapi.json`);
anything deployment-specific (group ids, subscription host) lives on the
`Panel` row.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import requests
from django.conf import settings
from django.utils import timezone

from .exceptions import (
    PanelAuthError,
    PanelConflict,
    PanelNotFound,
    PanelUnavailable,
    PanelValidationError,
)

log = logging.getLogger("caspintunel")

_TRANSIENT_STATUS = {500, 502, 503, 504}


def _unwrap(data, *keys) -> list:
    """PasarGuard list endpoints return {"<key>": [...]} or a bare list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in (*keys, "items", "data"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


class PasarGuardClient:
    """Thin wrapper around the panel API with token caching and typed errors."""

    def __init__(self, panel):
        self.panel = panel
        self.base = panel.base_url.rstrip("/")
        self.timeout = settings.PANEL_HTTP_TIMEOUT
        self._session = requests.Session()
        self._session.verify = panel.verify_ssl

    # -- auth -----------------------------------------------------------
    def _token(self, *, force: bool = False) -> str:
        p = self.panel
        if not force and p.token_cache and p.token_expires_at and p.token_expires_at > timezone.now():
            return p.token_cache
        token = self._authenticate()
        p.token_cache = token
        p.token_expires_at = timezone.now() + timedelta(seconds=settings.PANEL_TOKEN_TTL_SECONDS)
        p.save(update_fields=["token_cache", "token_expires_at", "updated_at"])
        return token

    def _authenticate(self) -> str:
        url = f"{self.base}/api/admin/token"
        try:
            resp = self._session.post(
                url,
                data={
                    "grant_type": "password",
                    "username": self.panel.admin_username,
                    "password": self.panel.admin_password_enc,
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise PanelUnavailable(f"cannot reach panel: {exc}") from exc
        if resp.status_code in (400, 401, 403):
            raise PanelAuthError("panel rejected admin credentials")
        if resp.status_code in _TRANSIENT_STATUS:
            raise PanelUnavailable(f"panel auth {resp.status_code}")
        if not resp.ok:
            raise PanelValidationError("panel auth failed", status_code=resp.status_code, body=resp.text)
        token = (resp.json() or {}).get("access_token")
        if not token:
            raise PanelAuthError("panel auth response had no access_token")
        return token

    # -- low-level request -------------------------------------------
    def _request(self, method: str, path: str, *, _retry_auth: bool = True, **kw) -> Any:
        url = f"{self.base}{path}"
        headers = kw.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._token()}"
        try:
            resp = self._session.request(method, url, headers=headers, timeout=self.timeout, **kw)
        except requests.RequestException as exc:
            raise PanelUnavailable(f"panel request failed: {exc}") from exc

        if resp.status_code == 401 and _retry_auth:
            self._token(force=True)
            return self._request(method, path, _retry_auth=False, **kw)
        if resp.status_code == 401:
            raise PanelAuthError("panel token rejected after refresh")
        if resp.status_code == 404:
            raise PanelNotFound(f"{method} {path} -> 404")
        if resp.status_code == 409:
            raise PanelConflict("resource already exists", status_code=409, body=resp.text)
        if resp.status_code in _TRANSIENT_STATUS:
            raise PanelUnavailable(f"panel {resp.status_code} on {path}")
        if not resp.ok:
            raise PanelValidationError(
                f"panel {resp.status_code} on {path}", status_code=resp.status_code, body=resp.text
            )
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # -- connectivity probe -----------------------------------------
    def check(self) -> bool:
        self._request("GET", "/api/system")
        return True

    # -- users ----------------------------------------------------
    def create_user(self, payload: dict) -> dict:
        return self._request("POST", "/api/user", json=payload)

    def get_user(self, username: str) -> dict:
        return self._request("GET", f"/api/user/{username}")

    def update_user(self, username: str, payload: dict) -> dict:
        return self._request("PUT", f"/api/user/{username}", json=payload)

    def delete_user(self, username: str) -> None:
        self._request("DELETE", f"/api/user/{username}")

    def reset_user_usage(self, username: str) -> dict:
        return self._request("POST", f"/api/user/{username}/reset")

    def revoke_subscription(self, username: str) -> dict:
        """Invalidates the account's current subscription link and issues a new
        one — every device using the old link is disconnected."""
        return self._request("POST", f"/api/user/{username}/revoke_sub")

    def set_user_disabled(self, username: str, disabled: bool) -> dict:
        return self._request("PUT", f"/api/user/{username}/disabled", json={"disabled": disabled})

    def list_users(self, *, search: str = "", limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        """Page of panel users, optionally filtered by a username substring.
        Returns (users, total)."""
        params = {"limit": int(limit), "offset": int(offset)}
        if search:
            params["search"] = search
        data = self._request("GET", "/api/users", params=params)
        users = _unwrap(data, "users")
        total = data.get("total", len(users)) if isinstance(data, dict) else len(users)
        return users, int(total or 0)

    def get_user_usage(self, username: str) -> dict:
        return self._request("GET", f"/api/user/{username}/usage")

    def list_expired_users(self) -> list[str]:
        data = self._request("GET", "/api/users/expired")
        return data if isinstance(data, list) else data.get("users", [])

    # -- monitoring ---------------------------------------------
    def system_stats(self) -> dict:
        return self._request("GET", "/api/system")

    def system_resources(self) -> dict:
        return self._request("GET", "/api/system/resources")

    def list_nodes(self) -> list[dict]:
        return _unwrap(self._request("GET", "/api/nodes"), "nodes")

    def list_groups(self) -> list[dict]:
        return _unwrap(self._request("GET", "/api/groups"), "groups")
