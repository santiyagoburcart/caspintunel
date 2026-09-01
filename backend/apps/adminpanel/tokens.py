"""
Lightweight JWTs for panel operators (the `Staff` model is separate from
AUTH_USER_MODEL, so SimpleJWT's user-bound flow doesn't fit). HS256 on
SECRET_KEY; claim `type` is `staff_access` / `staff_refresh` to keep them
distinct from customer tokens.
"""
from __future__ import annotations

import time
import uuid
from datetime import timedelta

import jwt
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

ACCESS_TTL = timedelta(minutes=getattr(settings, "STAFF_JWT_ACCESS_MIN", 30))
REFRESH_TTL = timedelta(days=getattr(settings, "STAFF_JWT_REFRESH_DAYS", 7))
_ALG = "HS256"
_BLACKLIST_PREFIX = "staff_rt_revoked:"


def _encode(payload: dict) -> str:
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALG)


def issue_tokens(staff) -> dict:
    now = timezone.now()
    base = {"staff_id": staff.id, "username": staff.username, "iat": now}
    access = _encode({**base, "type": "staff_access", "exp": now + ACCESS_TTL})
    refresh = _encode({**base, "type": "staff_refresh", "exp": now + REFRESH_TTL, "jti": uuid.uuid4().hex})
    return {"access": access, "refresh": refresh}


def decode(token: str, expected_type: str) -> dict:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALG])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    if expected_type == "staff_refresh":
        jti = payload.get("jti", "")
        if jti and cache.get(_BLACKLIST_PREFIX + jti):
            raise jwt.InvalidTokenError("refresh token already used")
    return payload


def revoke_refresh(payload: dict) -> None:
    """Blacklist a refresh token's jti until its natural expiry (rotation:
    every /auth/refresh/ retires the token it consumed, so a stolen refresh
    token is single-use)."""
    jti = payload.get("jti")
    if not jti:
        return
    ttl = int(payload.get("exp", 0) - time.time())
    if ttl > 0:
        cache.set(_BLACKLIST_PREFIX + jti, 1, ttl)
