"""Reseller portal auth + data (PAMP's per-admin portal, caspintunel side).

Login is PAMP's `PanelAdminBackend`: the username/password are checked by
asking the PasarGuard panel for a token (/api/admin/token). Resellers get their
own bearer session (`Authorization: Agency <token>`, 10 days like PAMP's
SESSION_COOKIE_AGE) — they are never caspintunel customers or staff, and these
tokens are accepted ONLY by the /api/v1/agency/portal/ endpoints.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework import authentication, exceptions, permissions

from .models import AdminGroup, PanelAdmin, ResellerSession

SESSION_AGE = timedelta(seconds=864000)      # PAMP: SESSION_COOKIE_AGE = 864000
FAIL_LIMIT, FAIL_WINDOW = 5, 15 * 60         # per-username lockout on top of the per-IP throttle


def portal_enabled() -> bool:
    from apps.settings_app.utils import get_setting

    return bool(get_setting("agency_portal_enabled", False))


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _fail_key(username: str) -> str:
    return "agency:portal:fail:" + hashlib.sha256(username.lower().encode()).hexdigest()[:32]


def locked_out(username: str) -> bool:
    return (cache.get(_fail_key(username)) or 0) >= FAIL_LIMIT


def verify_panel_credentials(username: str, password: str) -> bool:
    """PAMP PanelAdminBackend.authenticate, verbatim in effect."""
    if not username or not password:
        return False
    from .panel_api import PanelAPIClient, PanelAPIError

    try:
        client = PanelAPIClient()
    except PanelAPIError:
        return False
    client.username = username
    client.password = password
    return client.login()


def login(username: str, password: str, ip: str = "") -> str | None:
    username = (username or "").strip()
    if locked_out(username):
        raise exceptions.Throttled(detail="too many failed attempts for this username — try again later")
    if not verify_panel_credentials(username, password):
        key = _fail_key(username)
        cache.set(key, (cache.get(key) or 0) + 1, FAIL_WINDOW)
        return None
    cache.delete(_fail_key(username))
    token = secrets.token_urlsafe(32)
    ResellerSession.objects.create(username=username, key_hash=_hash(token),
                                   expires_at=timezone.now() + SESSION_AGE, ip=ip[:64])
    return token


class Reseller:
    """request.user for portal requests — not a Django user, not staff."""
    is_authenticated = True
    is_staff = is_superuser = False

    def __init__(self, username: str, session: ResellerSession):
        self.username, self.session = username, session

    @property
    def pk(self) -> str:
        # DRF's UserRateThrottle keys its bucket on request.user.pk; namespaced so a
        # reseller never shares a bucket with a customer account (integer pks)
        return f"agency:{self.username}"


class ResellerTokenAuthentication(authentication.BaseAuthentication):
    keyword = "Agency"

    def authenticate(self, request):
        auth = authentication.get_authorization_header(request).split()
        if not auth or auth[0].decode().lower() != self.keyword.lower():
            return None
        if len(auth) != 2:
            raise exceptions.AuthenticationFailed("invalid token header")
        s = ResellerSession.objects.filter(key_hash=_hash(auth[1].decode()), revoked=False,
                                           expires_at__gt=timezone.now()).first()
        if s is None:
            raise exceptions.AuthenticationFailed("session expired — log in again")
        now = timezone.now()
        if not s.last_used_at or now - s.last_used_at > timedelta(minutes=5):
            ResellerSession.objects.filter(pk=s.pk).update(last_used_at=now)
        return Reseller(s.username, s), s

    def authenticate_header(self, request):
        return self.keyword


class IsReseller(permissions.BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, Reseller)


def visible_usernames(username: str) -> tuple[str, list[str]]:
    """PAMP portal: a group owner sees owner + members (read-only), anyone else
    only themselves. Returns (mode, usernames)."""
    group = AdminGroup.get_group_for_owner(username)
    if group:
        return "group", group.get_all_usernames()
    return "single", [username]


def portal_payload(username: str) -> dict:
    from . import api, ledger
    from .enrich import _enrich, portal_state

    mode, names = visible_usernames(username)
    accounts = []
    for n in names:
        a = PanelAdmin.objects.filter(username=n).first()
        if a is None:
            continue
        row = api.admin_row(a)
        row.pop("groups", None)
        row.update({"deleted_used_fmt": _enrich(a)["deleted_used_fmt"], "portal": portal_state(a),
                    "admin_limit_fmt": a.admin_limit_fmt})
        accounts.append(row)
    if mode == "single" and not accounts:
        mode = "not_found"
    bal = ledger.balances()
    return {"username": username, "mode": mode, "accounts": accounts,
            "balances": {n: bal.get(n, 0) for n in names}}
