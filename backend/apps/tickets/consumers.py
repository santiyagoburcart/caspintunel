"""Live feed for the staff ticket inbox: `/ws/admin/tickets/?token=<staff access token>`.

Each staff member joins their own group (`staff_tickets_<id>`), because the
badge count depends on their topic scope; `notify._push` sends the events.
The DB stays the source of truth (`GET /admin/tickets/badge/`)."""
from __future__ import annotations

import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .notify import STAFF_GROUP


@database_sync_to_async
def _staff(token: str):
    import jwt

    from apps.adminpanel.tokens import decode, staff_for_payload

    try:
        payload = decode(token, "staff_access")
    except jwt.InvalidTokenError:
        return None
    staff = staff_for_payload(payload)
    if staff is None or not staff.has_perm("tickets.view"):
        return None
    return staff


class StaffTicketsConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        token = parse_qs((self.scope.get("query_string") or b"").decode()).get("token", [None])[0]
        staff = await _staff(token) if token else None
        if staff is None:
            await self.close(code=4401)
            return
        self.group_name = STAFF_GROUP.format(staff.id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if text_data == "ping":
            await self.send(text_data="pong")

    async def tickets_event(self, event):
        await self.send(text_data=json.dumps(event["payload"]))
