"""
Lightweight JWTs for panel operators (the `Staff` model is separate from
AUTH_USER_MODEL, so SimpleJWT's user-bound flow doesn't fit). HS256 on
SECRET_KEY; claim `type` is `staff_access` / `staff_refresh` to keep them
distinct from customer tokens.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone as dt_timezone

import jwt
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

ACCESS_TTL = timedelta(minutes=getattr(settings, "STAFF_JWT_ACCESS_MIN", 30))
REFRESH_TTL = timedelta(days=getattr(settings, "STAFF_JWT_REFRESH_DAYS", 7))
_ALG = "HS256"


def _encode(payload: dict) -> str:
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALG)


def issue_tokens(staff) -> dict:
    now = timezone.now()
    # "tv" = Staff.token_version at issue time; bumping it kills every token
    base = {"staff_id": staff.id, "username": staff.username, "iat": now, "tv": staff.token_version}
    access = _encode({**base, "type": "staff_access", "exp": now + ACCESS_TTL})
    refresh = _encode({**base, "type": "staff_refresh", "exp": now + REFRESH_TTL, "jti": uuid.uuid4().hex})
    return {"access": access, "refresh": refresh}


def decode(token: str, expected_type: str) -> dict:
    """Signature, expiry and type only — callers must then resolve the staff
    with `staff_for_payload` (token version / active check)."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALG])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    if expected_type == "staff_refresh":
        from apps.accounts.models import StaffRevokedToken

        jti = payload.get("jti", "")
        if not jti or StaffRevokedToken.objects.filter(jti=jti).exists():
            raise jwt.InvalidTokenError("refresh token already used")
    return payload


def staff_for_payload(payload: dict):
    """The active Staff a decoded token belongs to, or None when the account is
    gone/disabled or the token predates its last session revocation (password
    change, `revoke_staff_sessions`). Tokens without "tv" (issued before
    versioning) are rejected."""
    from apps.accounts.models import Staff

    staff = Staff.objects.filter(pk=payload.get("staff_id"), is_active=True).select_related("role").first()
    if staff is None or payload.get("tv") != staff.token_version:
        return None
    return staff


def revoke_refresh(payload: dict) -> bool:
    """Blacklist a refresh token's jti in the DB until its natural expiry
    (rotation: every /auth/refresh/ retires the token it consumed, so a stolen
    refresh token is single-use). Returns False if it was already revoked —
    the unique insert is the gate, so two concurrent refreshes with the same
    token can't both succeed."""
    from apps.accounts.models import StaffRevokedToken

    jti = payload.get("jti")
    if not jti:
        return False
    expires = datetime.fromtimestamp(int(payload.get("exp", 0)), tz=dt_timezone.utc)
    try:
        with transaction.atomic():
            StaffRevokedToken.objects.create(jti=jti, expires_at=expires)
    except IntegrityError:
        return False
    # housekeeping: rows past expiry can never matter again
    StaffRevokedToken.objects.filter(expires_at__lt=timezone.now()).delete()
    return True
