"""WebSocket consumer for the user-site notification bell.

Each connected user joins group `notifications_{user.id}`; `dispatch._deliver_site`
sends `notification.push` events into that group. The DB (`NotificationDelivery`)
stays the source of truth — this is only the real-time nudge.
"""
from __future__ import annotations

import json

from channels.generic.websocket import AsyncWebsocketConsumer


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
