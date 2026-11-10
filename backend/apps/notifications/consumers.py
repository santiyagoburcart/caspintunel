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

    async def ticket_event(self, event):
        # a ticket of this user changed (apps.tickets.notify) — the open chat refetches
        await self.send(text_data=json.dumps({"ticket_event": event["payload"]}))


@database_sync_to_async
def _staff_from_token(token: str, tenant_id: int | None = None):
    """Staff tokens are separate from customer JWTs (see adminpanel.tokens),
    so the customer-oriented JWTAuthMiddleware leaves scope["user"] anonymous
    for them — decode it here and require the payments permission."""
    import jwt

    from apps.adminpanel.tokens import decode, staff_for_payload

    try:
        payload = decode(token, "staff_access")
    except jwt.InvalidTokenError:
        return None
    staff = staff_for_payload(payload, tenant_id=tenant_id)
    if staff is None or not staff.has_perm("payment.view"):
        return None
    return staff


@database_sync_to_async
def _socket_tenant(scope):
    from apps.tenancy.middleware import resolve

    host = next((v.decode("latin-1") for k, v in scope.get("headers") or [] if k == b"host"), "")
    return resolve(host)


@database_sync_to_async
def _payments_group_for(scope):
    from apps.notifications.live import payments_group
    from apps.tenancy import context
    from apps.tenancy.middleware import resolve

    host = ""
    for k, v in scope.get("headers") or []:
        if k == b"host":
            host = v.decode("latin-1")
            break
    tid = resolve(host)
    if tid is None:
        return None
    return payments_group(None if tid == context.default_tenant_id() else tid)


class StaffPaymentsConsumer(AsyncWebsocketConsumer):
    """Live feed for the admin payments queue + pending-count badge."""

    async def connect(self):
        query = parse_qs((self.scope.get("query_string") or b"").decode())
        token = query.get("token", [None])[0]
        tid = await _socket_tenant(self.scope)                  # v1.52: a store's staff only on its own store's socket
        staff = await _staff_from_token(token, tid) if token else None
        if staff is None:
            await self.close(code=4401)
            return
        # v1.47 (multi-tenant Phase 5): the store this socket was opened on (Host) picks its live group — a store's panel
        # never hears our queue and ours never hears a store's
        group = await _payments_group_for(self.scope)
        if group is None:
            await self.close(code=4404)
            return
        self.group = group
        self.joined = True
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if getattr(self, "joined", False):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # client keep-alive ("ping") — some proxies drop idle sockets
        if text_data == "ping":
            await self.send(text_data="pong")

    async def payments_event(self, event):
        await self.send(text_data=json.dumps(event["payload"]))
