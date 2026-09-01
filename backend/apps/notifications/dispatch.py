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
    if not user.email or not settings.EMAIL_HOST:
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


def notify_user(user, *, title: str, body: str, ntype: str = NotificationType.EVENT,
                via_site: bool = True, via_bot: bool = False, via_email: bool = False,
                notification: Notification | None = None, staff=None) -> Notification:
    note = notification or Notification.objects.create(
        type=ntype, title=title, body=body, target_user=user,
        via_site=via_site, via_bot=via_bot, via_email=via_email, created_by_staff=staff,
    )

    plan = []
    if via_site:
        plan.append((DeliveryChannel.SITE, lambda: (DeliveryStatus.SENT, "")))
    if via_email:
        plan.append((DeliveryChannel.EMAIL, lambda: _deliver_email(user, title, body)))
    if via_bot:
        plan.append((DeliveryChannel.BOT, lambda: _deliver_bot(user, title, body)))

    for channel, fn in plan:
        status, error = fn()
        NotificationDelivery.objects.create(
            notification=note, user=user, channel=channel, status=status, error=error
        )
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
            ntype=notification.type, via_site=notification.via_site,
            via_bot=notification.via_bot, via_email=notification.via_email,
            notification=notification,
        )
        sent += 1
    return {"notification": notification.id, "recipients": sent}
