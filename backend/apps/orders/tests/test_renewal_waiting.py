"""One renewal at a time (v1.30.1, incident 2026-10-29): while a renewal of a service is
paid (queued) or its receipt is under review, a second one can't be bought — site, Mini
App (same API) and bot — and a paid renewal never replaces another one that still waits:
the extra order becomes `failed` and staff are alerted."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.common.models import AuditLog
from apps.orders.models import Order, OrderStatus, OrderType, ScheduledRenewal
from apps.orders.services import RenewalWaiting, create_order, quote_order, schedule_renewal, waiting_renewal
from apps.orders.tests.test_renew_same_account import (  # noqa: F401 — fixtures
    ACC, _api, _bot_user, _buttons, _pay, _service, bot, panel, plans, user,
)
from apps.payments_sms.models import Payment, PaymentStatus
from apps.payments_sms.services import reject_payment

pytestmark = pytest.mark.django_db


def _renew(user, svc, plan):
    return create_order(user=user, plan_id=plan.id, order_type=OrderType.RENEW, service_id=svc.id)


def test_second_renewal_is_refused_while_a_paid_one_waits(user, panel, plans, django_capture_on_commit_callbacks):
    a, b, _ = plans
    svc = _service(user, panel, a)
    first = _pay(_renew(user, svc, a), django_capture_on_commit_callbacks)
    assert first.status == OrderStatus.COMPLETED
    with pytest.raises(RenewalWaiting) as exc:
        _renew(user, svc, a)
    assert exc.value.waiting["state"] == "paid" and exc.value.waiting["order"].id == first.id
    assert "پرداخت شده" in exc.value.message("fa") and "already paid" in exc.value.message("en")
    with pytest.raises(RenewalWaiting):              # another plan doesn't get around it either
        _renew(user, svc, b)
    with pytest.raises(RenewalWaiting):
        quote_order(user=user, plan_id=a.id, order_type=OrderType.RENEW, service_id=svc.id)
    assert Order.objects.filter(type=OrderType.RENEW).count() == 1
    assert ScheduledRenewal.objects.get(service=svc).order_id == first.id


def test_renewal_with_a_receipt_under_review_blocks_until_rejected(user, panel, plans):
    a, _, _ = plans
    svc = _service(user, panel, a)
    o = _renew(user, svc, a)
    pay = Payment.objects.create(order=o, amount=o.amount_unique, status=PaymentStatus.PENDING)
    w = waiting_renewal(svc)
    assert w["state"] == "review" and w["order"].id == o.id
    with pytest.raises(RenewalWaiting) as exc:
        _renew(user, svc, a)
    assert "بررسی" in exc.value.message("fa")
    reject_payment(pay.id, reason="wrong amount")
    assert waiting_renewal(svc) is None
    assert _renew(user, svc, a).id != o.id


def test_an_applied_renewal_frees_the_service_again(user, panel, plans, django_capture_on_commit_callbacks):
    a, _, _ = plans
    svc = _service(user, panel, a)
    _pay(_renew(user, svc, a), django_capture_on_commit_callbacks)
    ScheduledRenewal.objects.filter(service=svc).update(applied_at=timezone.now())
    assert waiting_renewal(svc) is None
    second = _pay(_renew(user, svc, a), django_capture_on_commit_callbacks)
    sr = ScheduledRenewal.objects.get(service=svc)          # the one row per service is reused
    assert sr.order_id == second.id and sr.applied_at is None


def test_a_paid_renewal_never_replaces_a_waiting_one(user, panel, plans, monkeypatch,
                                                     django_capture_on_commit_callbacks):
    """Two invoices made before either was paid (e.g. two plans) and both paid: the first
    stays queued, the second is `failed`, staff are alerted and the customer is told."""
    import apps.common.staff_alert as staff_alert
    import apps.notifications.dispatch as dispatch

    alerts, notices = [], []
    monkeypatch.setattr(staff_alert, "alert_staff", lambda text, **kw: alerts.append((text, kw)) or 1)
    monkeypatch.setattr(dispatch, "notify_user", lambda u, **kw: notices.append(kw))
    a, b, _ = plans
    svc = _service(user, panel, a)
    o1 = _renew(user, svc, a)
    o2 = _renew(user, svc, b)
    _pay(o1, django_capture_on_commit_callbacks)
    _pay(o2, django_capture_on_commit_callbacks)
    o1.refresh_from_db(); o2.refresh_from_db(); svc.refresh_from_db()
    assert o1.status == OrderStatus.COMPLETED
    assert o2.status == OrderStatus.FAILED and o2.amount_unique_lock is None
    sr = ScheduledRenewal.objects.get(service=svc)
    assert sr.order_id == o1.id and sr.plan_id == a.id
    assert svc.current_plan_id == a.id                      # the failed one didn't switch the plan
    log = AuditLog.objects.get(action="renewal.conflict")
    assert log.target_id == o2.id and log.detail["waiting_order"] == o1.id
    assert len(alerts) == 1 and f"#{o2.id}" in alerts[0][0] and f"#{o1.id}" in alerts[0][0]
    assert alerts[0][1]["perm"] == "payment.approve"
    assert any("در انتظار" in n.get("body", "") for n in notices)


def test_schedule_renewal_is_idempotent_for_the_same_order(user, panel, plans, django_capture_on_commit_callbacks):
    a, _, _ = plans
    svc = _service(user, panel, a)
    o = _pay(_renew(user, svc, a), django_capture_on_commit_callbacks)
    schedule_renewal(o)                                       # a task retry: no conflict, same row
    assert ScheduledRenewal.objects.filter(service=svc).count() == 1


def test_incident_replay_sms_paid_then_second_renewal_refused(user, panel, plans, django_capture_on_commit_callbacks):
    """2026-10-29: renewal paid by SMS, then a second renewal with a screenshot of the same
    transfer. Now the second invoice can't even be created (site API answers 409)."""
    a, _, _ = plans
    svc = _service(user, panel, None)                         # manually linked, no plan
    c = _api(user)
    r = c.post(f"/api/v1/services/{svc.id}/renew/", {"plan": a.id}, format="json")
    assert r.status_code == 201
    order = Order.objects.get(pk=r.data["order"]["id"])
    _pay(order, django_capture_on_commit_callbacks)
    r = c.post(f"/api/v1/services/{svc.id}/renew/", {"plan": a.id}, format="json")
    assert r.status_code == 409 and r.data["code"] == "renewal_waiting"
    assert "با پایان حجم/زمان فعلی اعمال می‌شود" in r.data["detail"]
    r = c.post("/api/v1/orders/", {"plan": a.id, "type": "renew", "service": svc.id}, format="json")
    assert r.status_code == 400 and "renewal_waiting" in str(r.data["code"])
    r = c.post("/api/v1/orders/quote/", {"plan": a.id, "type": "renew", "service": svc.id, "lang": "en"},
               format="json")
    assert r.status_code == 409 and "already paid" in r.data["detail"]
    assert Order.objects.filter(type=OrderType.RENEW).count() == 1


def test_service_api_shows_the_waiting_renewal(user, panel, plans, django_capture_on_commit_callbacks):
    a, b, _ = plans
    svc = _service(user, panel, a)
    c = _api(user)
    r = c.get(f"/api/v1/services/{svc.id}/renew-info/")
    assert r.data["can_renew"] is True and r.data["pending_renewal"] is None
    _pay(_renew(user, svc, b), django_capture_on_commit_callbacks)
    r = c.get(f"/api/v1/services/{svc.id}/renew-info/")
    assert r.data["can_renew"] is False and r.data["plans"] == []
    pr = r.data["pending_renewal"]
    assert pr["state"] == "paid" and pr["plan_id"] == b.id and pr["plan_name"] == "طلایی"
    assert pr["plan_name_en"] == "Gold" and pr["applies_by"] is not None
    assert "با پایان حجم/زمان فعلی اعمال می‌شود" in r.data["message"]
    rows = c.get("/api/v1/services/").data
    rows = rows.get("results", rows) if isinstance(rows, dict) else rows
    row = next(x for x in rows if x["id"] == svc.id)
    assert row["pending_renewal"]["plan_id"] == b.id


# --- bot ---------------------------------------------------------------------------
def test_bot_service_shows_the_waiting_renewal_and_no_renew_button(bot, user, panel, plans,
                                                                    django_capture_on_commit_callbacks):
    a, b, _ = plans
    _bot_user(user)
    svc = _service(user, panel, a)
    _pay(_renew(user, svc, b), django_capture_on_commit_callbacks)
    sent = bot.click(f"s:{svc.id}")
    text = sent[-1][0]
    assert "تمدید پرداخت شد — با پایان حجم/زمان فعلی اعمال می‌شود" in text and "طلایی" in text
    assert f"s:{svc.id}:rn" not in [d for _, d in _buttons(sent)]
    sent = bot.click(f"s:{svc.id}:rn")                       # an older message's renew button
    assert "تمدید پرداخت شد" in sent[-1][0]
    assert not any(d and d.startswith("rn:") for _, d in _buttons(sent))
    sent = bot.click(f"rn:{svc.id}:{a.id}")                  # an older one-tap button
    assert "تمدید پرداخت شد" in sent[-1][0]
    assert Order.objects.filter(type=OrderType.RENEW).count() == 1


def test_bot_review_state_text(bot, user, panel, plans):
    a, _, _ = plans
    _bot_user(user)
    svc = _service(user, panel, a)
    o = _renew(user, svc, a)
    Payment.objects.create(order=o, amount=o.amount_unique, status=PaymentStatus.PENDING)
    sent = bot.click(f"s:{svc.id}:rnp")
    assert "رسید تمدید در حال بررسی است" in sent[-1][0]


def test_staff_alert_helper_dedupes_and_falls_back(monkeypatch):
    from django.core.cache import cache

    from apps.common.staff_alert import alert_staff
    from apps.telegram import config

    cache.clear()
    sent = []

    class Client:
        def send_message(self, chat, text, parse_mode=None):
            sent.append((chat, text))

    monkeypatch.setattr(config, "sales_client", lambda: None)
    monkeypatch.setattr(config, "backup_client", lambda: Client())
    monkeypatch.setattr(config, "get_bot_config", lambda t: type("C", (), {"backup_chat_id": -100})())
    assert alert_staff("hi", perm="payment.approve", dedupe_key="k1") == 1
    assert alert_staff("hi", perm="payment.approve", dedupe_key="k1") == 0
    assert sent == [(-100, "hi")]
