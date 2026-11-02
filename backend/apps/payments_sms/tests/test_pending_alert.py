"""v1.33 unconfirmed payment alert: pending longer than N minutes → one Telegram + panel alert
(never repeated), a silent "resolved" follow-up; setting 0 = off; old rows ignored."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.payments_sms.models import Payment, PaymentMethod, PaymentStatus
from apps.payments_sms.pending_alert import run
from apps.payments_sms.tests.test_blu import env, make_order  # noqa: F401
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db(transaction=True)


def pending(order, minutes_ago, method=PaymentMethod.CARD_MANUAL):
    p = Payment.objects.create(order=order, method=method, amount=order.amount_unique, status=PaymentStatus.PENDING)
    Payment.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_ago))
    return p


def test_one_alert_after_n_minutes_then_resolved(env):  # noqa: F811
    o = make_order()
    p = pending(o, 3)
    assert run()["alerted"] == 0                          # not yet 5 minutes
    Payment.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(minutes=6))
    assert run()["alerted"] == 1
    text, kw = env["alerts"][0]
    assert p.tx_number in text and f"/payments/{p.id}" in text and kw["perm"] == "payment.approve"
    assert ("payment_pending_alert", {"order_id": o.id, "payment_id": p.id, "minutes": 6, "tx": p.tx_number}) in env["events"]
    assert run()["alerted"] == 0 and len(env["alerts"]) == 1          # never repeated
    from apps.payments_sms.services import approve_payment

    approve_payment(p.id)
    assert run()["resolved"] == 1
    assert env["alerts"][-1][1]["silent"] is True and "تأیید شد" in env["alerts"][-1][0]
    assert run()["resolved"] == 0


def test_setting_and_lookback(env):  # noqa: F811
    set_setting("pending_payment_alert_minutes", 0, "int")
    pending(make_order(), 30)
    assert run()["alerted"] == 0                          # 0 = off
    set_setting("pending_payment_alert_minutes", 10, "int")
    pending(make_order(175663, "b"), 60 * 30)             # older than 24 h: ignored
    assert run()["alerted"] == 1
