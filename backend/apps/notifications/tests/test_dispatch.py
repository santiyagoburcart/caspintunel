import pytest

from apps.accounts.models import User
from apps.notifications.dispatch import notify_user
from apps.notifications.models import DeliveryChannel, DeliveryStatus, NotificationDelivery

pytestmark = pytest.mark.django_db


def test_site_only_notification():
    u = User.objects.create_user("u", "Str0ngPass!")
    note = notify_user(u, title="t", body="b")
    assert note.target_user == u
    d = NotificationDelivery.objects.get(notification=note)
    assert d.channel == DeliveryChannel.SITE and d.status == DeliveryStatus.SENT


def test_email_channel_records_failure_without_raising(settings):
    settings.EMAIL_HOST = ""  # not configured
    u = User.objects.create_user("u", "Str0ngPass!", email="u@example.com")
    note = notify_user(u, title="t", body="b", via_site=True, via_email=True)
    email = NotificationDelivery.objects.get(notification=note, channel=DeliveryChannel.EMAIL)
    assert email.status == DeliveryStatus.FAILED
    assert NotificationDelivery.objects.filter(
        notification=note, channel=DeliveryChannel.SITE, status=DeliveryStatus.SENT
    ).exists()


def test_bot_channel_fails_gracefully_without_telegram_id():
    u = User.objects.create_user("u", "Str0ngPass!")
    note = notify_user(u, title="t", body="b", via_bot=True)
    bot = NotificationDelivery.objects.get(notification=note, channel=DeliveryChannel.BOT)
    assert bot.status == DeliveryStatus.FAILED
    assert "telegram_id" in bot.error


def test_email_sent_when_smtp_configured(settings):
    settings.EMAIL_HOST = "mail.test"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    u = User.objects.create_user("u", "Str0ngPass!", email="u@example.com")
    from django.core import mail

    note = notify_user(u, title="hello", body="body", via_site=False, via_email=True)
    assert len(mail.outbox) == 1 and mail.outbox[0].subject == "hello"
    assert NotificationDelivery.objects.get(
        notification=note, channel=DeliveryChannel.EMAIL
    ).status == DeliveryStatus.SENT
