"""
Multi-channel notification delivery. Every channel is isolated: a failure in
one (SMTP down, Telegram filtered) is logged on its `NotificationDelivery` row
and never blocks the others or raises.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import (
    DeliveryChannel,
    DeliveryStatus,
    Notification,
    NotificationDelivery,
    NotificationType,
)

log = logging.getLogger("caspintunel")


def _deliver_email(user, title, body) -> tuple[str, str]:
    from apps.common.mail import mail_configured

    if not user.email or not mail_configured():
        return DeliveryStatus.FAILED, "no email / SMTP not configured"
    try:
        send_mail(title, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
        return DeliveryStatus.SENT, ""
    except Exception as exc:  # noqa: BLE001
        log.warning("notify email to %s failed: %s", user.email, exc)
        return DeliveryStatus.FAILED, str(exc)[:250]


def _deliver_bot(user, title, body) -> tuple[str, str]:
    if not user.telegram_id:
        return DeliveryStatus.FAILED, "user has no telegram_id"
    try:
        from apps.telegram.config import sales_client

        client = sales_client()
        if client is None:
            return DeliveryStatus.FAILED, "sales bot not configured"
        client.send_message(user.telegram_id, f"<b>{title}</b>\n\n{body}")
        return DeliveryStatus.SENT, ""
    except Exception as exc:  # noqa: BLE001
        log.warning("notify bot to %s failed: %s", user.telegram_id, exc)
        return DeliveryStatus.FAILED, str(exc)[:250]


def _unread_site_count(user) -> int:
    return NotificationDelivery.objects.filter(
        user=user, channel=DeliveryChannel.SITE
    ).exclude(status=DeliveryStatus.READ).count()


def _deliver_site(user, note: Notification, delivery: NotificationDelivery) -> tuple[str, str]:
    """Pushes the just-created delivery over the user's WebSocket group, if
    Channels is configured and they're connected — the DB row (already
    created by the caller) is the actual source of truth either way, this is
    just the real-time nudge so the bell badge updates without a refetch."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return DeliveryStatus.SENT, ""
        async_to_sync(layer.group_send)(
            f"notifications_{user.id}",
            {
                "type": "notification.push",
                "payload": {
                    "id": delivery.id,
                    "type": note.type,
                    "title": note.title,
                    "title_en": note.title_en,
                    "body": note.body,
                    "body_en": note.body_en,
                    "created_at": note.created_at.isoformat(),
                    "is_read": False,
                },
                "unread_count": _unread_site_count(user),
            },
        )
        return DeliveryStatus.SENT, ""
    except Exception as exc:  # noqa: BLE001
        log.warning("notify site-push to user %s failed: %s", user.id, exc)
        return DeliveryStatus.FAILED, str(exc)[:250]


def notify_user(user, *, title: str, body: str, title_en: str = "", body_en: str = "",
                ntype: str = NotificationType.EVENT,
                via_site: bool = True, via_bot: bool = False, via_email: bool = False,
                notification: Notification | None = None, staff=None) -> Notification:
    note = notification or Notification.objects.create(
        type=ntype, title=title, body=body, title_en=title_en, body_en=body_en,
        target_user=user, via_site=via_site, via_bot=via_bot, via_email=via_email, created_by_staff=staff,
    )

    channels: list[str] = []
    if via_site:
        channels.append(DeliveryChannel.SITE)
    if via_email:
        channels.append(DeliveryChannel.EMAIL)
    if via_bot:
        channels.append(DeliveryChannel.BOT)

    for channel in channels:
        # created first (status defaults to SENT) so _deliver_site has a real
        # delivery id to push before the actual send outcome is known
        delivery = NotificationDelivery.objects.create(notification=note, user=user, channel=channel)
        if channel == DeliveryChannel.EMAIL:
            status, error = _deliver_email(user, note.title, note.body)
        elif channel == DeliveryChannel.BOT:
            status, error = _deliver_bot(user, note.title, note.body)
        else:
            status, error = _deliver_site(user, note, delivery)
        if status != delivery.status or error:
            delivery.status = status
            delivery.error = error
            delivery.save(update_fields=["status", "error"])
    return note


def broadcast(notification: Notification, *, batch=None) -> dict:
    """Fan a stored broadcast Notification out to every active user."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    users = User.objects.filter(is_active=True)
    if batch:
        users = users[:batch]
    sent = 0
    for user in users.iterator():
        notify_user(
            user, title=notification.title, body=notification.body,
            title_en=notification.title_en, body_en=notification.body_en,
            ntype=notification.type, via_site=notification.via_site,
            via_bot=notification.via_bot, via_email=notification.via_email,
            notification=notification,
        )
        sent += 1
    return {"notification": notification.id, "recipients": sent}
