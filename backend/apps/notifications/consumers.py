"""WebSocket consumer for the user-site notification bell.

Each connected user joins group `notifications_{user.id}`; `dispatch._deliver_site`
sends `notification.push` events into that group. The DB (`NotificationDelivery`)
stays the source of truth — this is only the real-time nudge.
"""
from __future__ import annotations

import json

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .live import STAFF_PAYMENTS_GROUP


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.group_name = f"notifications_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_push(self, event):
        await self.send(text_data=json.dumps({
            "notification": event["payload"],
            "unread_count": event["unread_count"],
        }))


@database_sync_to_async
def _staff_from_token(token: str):
    """Staff tokens are separate from customer JWTs (see adminpanel.tokens),
    so the customer-oriented JWTAuthMiddleware leaves scope["user"] anonymous
    for them — decode it here and require the payments permission."""
    import jwt

    from apps.adminpanel.tokens import decode, staff_for_payload

    try:
        payload = decode(token, "staff_access")
    except jwt.InvalidTokenError:
        return None
    staff = staff_for_payload(payload)
    if staff is None or not staff.has_perm("payment.view"):
        return None
    return staff


class StaffPaymentsConsumer(AsyncWebsocketConsumer):
    """Live feed for the admin payments queue + pending-count badge."""

    async def connect(self):
        query = parse_qs((self.scope.get("query_string") or b"").decode())
        token = query.get("token", [None])[0]
        staff = await _staff_from_token(token) if token else None
        if staff is None:
            await self.close(code=4401)
            return
        self.joined = True
        await self.channel_layer.group_add(STAFF_PAYMENTS_GROUP, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if getattr(self, "joined", False):
            await self.channel_layer.group_discard(STAFF_PAYMENTS_GROUP, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # client keep-alive ("ping") — some proxies drop idle sockets
        if text_data == "ping":
            await self.send(text_data="pong")

    async def payments_event(self, event):
        await self.send(text_data=json.dumps(event["payload"]))
