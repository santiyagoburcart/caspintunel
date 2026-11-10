"""v1.51.1 (TX-000078): a paid renewal is queued until the current volume / time ends — the customer is told at payment
(site + bot: «تمدید پرداخت شد…» with the new plan, volume, days and when it applies) and the admin panel shows the queued
renewal on the service instead of only the new plan's name next to the old volume."""
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.notifications.models import DeliveryChannel, Notification, NotificationDelivery
from apps.orders.models import OrderType, ScheduledRenewal
from apps.orders.services import create_order
from apps.orders.tests.test_renew_same_account import (  # noqa: F401 — fixtures
    _pay, _service, panel, plans, user,
)
from apps.panel.models import ServiceStatus
from apps.payments_sms.tests.test_blu import staff_client

pytestmark = pytest.mark.django_db
TITLE = "تمدید پرداخت شد — با پایان حجم/زمان فعلی اعمال می‌شود"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    cache.clear()
    sent = []
    monkeypatch.setattr("apps.telegram.config.sales_client",
                        lambda: type("B", (), {"send_message": lambda self, chat, text, **kw: sent.append((chat, text))})())
    return sent


def _renew(user, svc, plan):
    return create_order(user=user, plan_id=plan.id, order_type=OrderType.RENEW, service_id=svc.id)


def test_customer_is_told_at_payment_with_plan_volume_days_and_when(user, panel, plans, _clean,
                                                                    django_capture_on_commit_callbacks):
    from apps.common.jalali import to_jalali_str

    a, b, _ = plans
    user.telegram_id = 4141
    user.save(update_fields=["telegram_id"])
    svc = _service(user, panel, a)                                  # 19 of 20 GB used, expires in 2 days
    order = _pay(_renew(user, svc, b), django_capture_on_commit_callbacks)
    assert ScheduledRenewal.objects.get(service=svc).applied_at is None   # still queued, nothing applied
    n = Notification.objects.get(target_user=user, title=TITLE)
    assert "طلایی · 200 گیگ · 30 روز" in n.body and to_jalali_str(svc.expire_at) in n.body
    assert "Gold · 200 GB · 30 days" in n.body_en and "whichever comes first" in n.body_en
    channels = set(NotificationDelivery.objects.filter(notification=n).values_list("channel", flat=True))
    assert channels == {DeliveryChannel.SITE, DeliveryChannel.BOT}
    assert _clean and _clean[-1][0] == 4141 and "طلایی" in _clean[-1][1]
    # fulfilment running again for the same order never repeats it
    from apps.orders.tasks import _notify_renewal_queued

    _notify_renewal_queued(order)
    assert Notification.objects.filter(target_user=user, title=TITLE).count() == 1


def test_an_ended_service_says_within_a_few_minutes(user, panel, plans, django_capture_on_commit_callbacks):
    a, _, _ = plans
    svc = _service(user, panel, a)
    svc.status, svc.expire_at = ServiceStatus.EXPIRED, timezone.now() - timedelta(hours=1)
    svc.save(update_fields=["status", "expire_at"])
    _pay(_renew(user, svc, a), django_capture_on_commit_callbacks)
    n = Notification.objects.get(target_user=user, title=TITLE)
    assert "ظرف چند دقیقه" in n.body and "within a few minutes" in n.body_en
    assert not NotificationDelivery.objects.filter(notification=n, channel=DeliveryChannel.BOT).exists()  # no Telegram


def test_admin_service_shows_the_queued_renewal_until_it_applies(user, panel, plans, django_capture_on_commit_callbacks):
    a, b, _ = plans
    svc = _service(user, panel, a)
    admin = staff_client("super", "prn-boss")
    row = next(r for r in admin.get("/api/v1/admin/services/").json()["results"] if r["id"] == svc.id)
    assert row["pending_renewal"] is None
    order = _pay(_renew(user, svc, b), django_capture_on_commit_callbacks)
    row = next(r for r in admin.get("/api/v1/admin/services/").json()["results"] if r["id"] == svc.id)
    p = row["pending_renewal"]
    assert (p["plan"], p["plan_en"], p["data_limit"], p["duration_days"]) == ("طلایی", "Gold", b.data_limit, 30)
    assert p["order_id"] == order.id and p["applies_by"] is not None and p["applies_soon"] is False
    assert row["data_limit"] == svc.data_limit                     # the current cycle's volume is still what it is
    ScheduledRenewal.objects.filter(service=svc).update(applied_at=timezone.now())
    row = next(r for r in admin.get("/api/v1/admin/services/").json()["results"] if r["id"] == svc.id)
    assert row["pending_renewal"] is None
