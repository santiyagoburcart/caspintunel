"""JWT auth for Channels WebSocket connections.

The app uses JWT everywhere instead of Django sessions, so Channels' default
session-based AuthMiddlewareStack doesn't apply. The browser can't set an
Authorization header on a WebSocket handshake, so the access token is passed
as a `?token=` query-string param instead.
"""
from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _get_user(token: str):
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    from django.contrib.auth import get_user_model

    try:
        validated = AccessToken(token)
        user_id = validated["user_id"]
    except (TokenError, KeyError):
        return AnonymousUser()

    User = get_user_model()
    return User.objects.filter(pk=user_id, is_active=True).first() or AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query = parse_qs((scope.get("query_string") or b"").decode())
        token = query.get("token", [None])[0]
        scope["user"] = await _get_user(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)
