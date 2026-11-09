"""Multi-tenant Phase 5 (v1.47): payments + SMS per store.

* Unique-amount pools per store (unique (tenant, amount_unique_lock)); agency payments share OUR pool only.
* A device token works only on its own store's domain; an SMS matches only that store's orders; agency payments never.
* The store's payments queue / cards / devices / sources / SMS log in its panel; Blu never shown there.
* Alerts, browser push and the live payments socket stay inside the store.
"""
from decimal import Decimal

import pytest
from asgiref.sync import async_to_sync
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Staff, User
from apps.orders.models import Order, OrderStatus, OrderType
from apps.orders.services import _assign_unique_amount
from apps.panel.models import Panel
from apps.payments_sms.models import BankCard, Payment, PaymentStatus, SmsAppDevice, SmsMessage, SmsSource
from apps.payments_sms.tests.test_blu import staff_client
from apps.plans.models import Plan
from apps.tenancy import context
from apps.tenancy.models import Tenant, TenantDomain

pytestmark = pytest.mark.django_db
HOST = "shop-p5.example"
SENDER = "+989999987641"


@pytest.fixture
def panel(_default_tenant):
    return Panel.objects.create(name="P", base_url="https://p.test", admin_username="a", admin_password_enc="p", is_active=True)


@pytest.fixture
def store(panel):
    t = Tenant.objects.create(slug="s5", name="Store Five", status="active", reseller_username="s5admin")
    TenantDomain.objects.create(tenant=t, host=HOST, state="active")
    from apps.settings_app.models import TenantBranding

    with context.tenant_context(t.pk):
        TenantBranding.objects.create(site_name_fa="فروشگاه پنج", site_name_en="Store Five")
    return t


@pytest.fixture(autouse=True)
def no_fulfil(monkeypatch):
    from apps.orders import tasks

    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda *a, **k: None)


def _in(t):
    return context.tenant_context(t.pk)


def _order(panel, amount, name="c"):
    u = User.objects.create_user(f"{name}{User.objects.count()}", "Str0ngPass!")
    plan = Plan.objects.create(panel=panel, name_fa="p", price=Decimal("100000"), data_limit=1024 ** 3, duration_days=30)
    o = Order(user=u, plan=plan, type=OrderType.NEW, status=OrderStatus.PENDING_PAYMENT, amount=Decimal("100000"),
              unique_expire_at=timezone.now() + timezone.timedelta(minutes=30), requested_account_name=f"{name}_acc")
    o.amount_unique = o.amount_unique_lock = Decimal(amount)
    o.save()
    return o


def _device():
    SmsSource.objects.create(phone_number=SENDER, description="bank")
    return SmsAppDevice.objects.create(name="phone", is_active=True)


def _sms(host, device, toman):
    c = APIClient(HTTP_HOST=host) if host else APIClient()
    c.credentials(HTTP_X_DEVICE_TOKEN=device.api_token)
    text = f"بلو\nواریز پول\nپویا عزیز،{toman * 10:,} ریال به حساب شخصی شما نشست.\nموجودی: 1 ریال"
    return c.post("/api/v1/payments/sms/inbound/", {"text": text, "sender": SENDER}, format="json")


# ------------------------------------------------------------------ pools
def test_two_stores_may_hold_the_same_amount_but_one_store_never_twice(store, panel):
    ours = _order(panel, 175662)
    with _in(store):
        theirs = _order(panel, 175662, "s")
        assert theirs.amount_unique_lock == ours.amount_unique_lock
        from django.db import IntegrityError, transaction

        with pytest.raises(IntegrityError), transaction.atomic():
            _order(panel, 175662, "s2")


def test_only_our_store_skips_the_amounts_agency_payments_hold(store, panel, monkeypatch):
    from apps.agency import billing

    monkeypatch.setattr(billing, "agency_locked_amounts", lambda: {Decimal(100200)})
    monkeypatch.setattr("apps.orders.services._surcharge_range", lambda: [200, 201])
    u = User.objects.create_user("pool1", "Str0ngPass!")
    plan = Plan.objects.create(panel=panel, name_fa="p", price=Decimal("100000"), duration_days=30)
    mk = lambda: Order(user=u, plan=plan, type=OrderType.NEW, status=OrderStatus.PENDING_PAYMENT, amount=Decimal("100000"),
                       unique_expire_at=timezone.now() + timezone.timedelta(minutes=30))
    o = mk()
    _assign_unique_amount(o, Decimal("100000"))
    assert o.amount_unique == 100201                          # ours: 100,200 is the agency's
    with _in(store):
        u2 = User.objects.create_user("pool2", "Str0ngPass!")
        o2 = Order(user=u2, plan=Plan.objects.create(panel=panel, name_fa="p", price=Decimal("100000"), duration_days=30),
                   type=OrderType.NEW, status=OrderStatus.PENDING_PAYMENT, amount=Decimal("100000"),
                   unique_expire_at=timezone.now() + timezone.timedelta(minutes=30))
        _assign_unique_amount(o2, Decimal("100000"))
        assert o2.amount_unique == 100200                     # a store's own pool


# ------------------------------------------------------------------ SMS per store
def test_a_store_sms_approves_only_that_stores_order(store, panel):
    ours = _order(panel, 175662)
    with _in(store):
        theirs = _order(panel, 175662, "s")
        dev = _device()
    r = _sms(HOST, dev, 175662)
    assert r.status_code in (200, 201), r.content
    with _in(store):
        theirs.refresh_from_db()
        assert theirs.status == OrderStatus.PAID
        assert Payment.objects.get(order=theirs).status == PaymentStatus.APPROVED
        assert SmsMessage.objects.count() == 1
    ours.refresh_from_db()
    assert ours.status == OrderStatus.PENDING_PAYMENT and not SmsMessage.objects.exists()


def test_device_tokens_only_work_on_their_own_store(store, panel):
    ours_dev = _device()
    with _in(store):
        their_dev = _device()
    assert _sms(None, their_dev, 1000).status_code in (401, 403)       # a store's token on our domain
    assert _sms(HOST, ours_dev, 1000).status_code in (401, 403)        # our token on the store's domain
    c = APIClient(HTTP_HOST=HOST)
    c.credentials(HTTP_X_DEVICE_TOKEN=their_dev.api_token)
    ping = c.get("/api/v1/payments/sms/ping/").json()
    assert ping["store"] == "فروشگاه پنج" and ping["device"] == "phone"
    assert APIClient(HTTP_HOST=HOST).post("/api/v1/payments/blu/webhook/", {}).status_code == 404   # Blu stays ours


def test_a_store_sms_never_matches_an_agency_payment(store, panel, monkeypatch):
    from apps.agency import billing

    called = []
    real_open_at = billing.open_at
    with _in(store):
        assert not billing.open_at(timezone.now()).exists() and billing.paid_duplicate(1000, timezone.now()) is None
        dev = _device()
    monkeypatch.setattr(billing, "approve_payment", lambda *a, **k: called.append(a))
    r = _sms(HOST, dev, 123456)
    assert r.status_code in (200, 201) and r.json()["matched"] is False and not called
    assert real_open_at is billing.open_at


# ------------------------------------------------------------------ the store's payments panel
def test_store_panel_shows_only_its_own_queue_and_settings(store, panel):
    ours = _order(panel, 200001)
    Payment.objects.create(order=ours, amount=ours.amount_unique, status=PaymentStatus.PENDING)
    BankCard.objects.create(card_number="6037990000000001", holder_name="ours")
    with _in(store):
        theirs = _order(panel, 200001, "s")
        tp = Payment.objects.create(order=theirs, amount=theirs.amount_unique, status=PaymentStatus.PENDING)
    boss = staff_client("super", "p5-boss")
    boss.defaults["HTTP_HOST"] = HOST
    rows = boss.get("/api/v1/admin/payments/pending/").json()["results"]
    assert [r["order_id"] for r in rows] == [theirs.pk] and rows[0]["blu_prefill"] is None
    r = boss.post("/api/v1/admin/cards/", {"card_number": "6037991111111111", "holder_name": "reseller", "bank_name": "Melli"},
                  format="json")
    assert r.status_code == 201, r.content
    assert [c["holder_name"] for c in boss.get("/api/v1/admin/cards/").json()["results"]] == ["reseller"]
    assert boss.post("/api/v1/admin/sms-devices/", {"name": "reseller phone"}, format="json").status_code == 201
    assert boss.post("/api/v1/admin/sms-sources/", {"phone_number": "+989121234567", "description": "bank"},
                     format="json").status_code == 201
    assert boss.get("/api/v1/admin/sms-log/").status_code == 200
    assert boss.get("/api/v1/admin/payments/blu-transactions/").status_code in (403, 404)
    assert boss.get("/api/v1/admin/transactions/").status_code in (403, 404)
    assert boss.post(f"/api/v1/admin/payments/{tp.pk}/approve/", {}, format="json").status_code == 200
    with _in(store):
        tp.refresh_from_db()
        assert tp.status == PaymentStatus.APPROVED
        assert BankCard.objects.count() == 1 and SmsAppDevice.objects.count() == 1
    assert list(BankCard.objects.values_list("holder_name", flat=True)) == ["ours"]
    assert boss.post(f"/api/v1/admin/payments/{Payment.objects.get(order=ours).pk}/approve/", {}, format="json").status_code == 404


def test_store_checkout_timer_is_its_own(store):
    boss = staff_client("super", "p5-set")
    boss.defaults["HTTP_HOST"] = HOST
    r = boss.put("/api/v1/admin/settings/", {"unique_amount_reservation_minutes": 45}, format="json")
    assert r.status_code == 200, r.content
    from apps.settings_app.utils import get_setting

    with _in(store):
        assert get_setting("unique_amount_reservation_minutes", 30) == 45
    assert get_setting("unique_amount_reservation_minutes", 30) == 30


# ------------------------------------------------------------------ alerts, push, live socket
def test_store_alerts_never_reach_our_staff_or_backup_chat(store, monkeypatch):
    sent = []

    class Bot:
        def send_message(self, chat, text, **kw):
            sent.append((chat, text))

    from apps.telegram import config

    monkeypatch.setattr(config, "sales_client", lambda: Bot())
    monkeypatch.setattr(config, "our_sales_client", lambda: Bot())   # v1.49: staff DMs use our bot
    monkeypatch.setattr(config, "backup_client", lambda: Bot())
    monkeypatch.setattr(config, "get_bot_config", lambda t: type("C", (), {"backup_chat_id": -100})())
    s = Staff(username="ourstaff", is_superadmin=True, telegram_id=777)
    s.set_password("x-Str0ng!"); s.save()
    from apps.common.staff_alert import alert_staff

    with _in(store):
        assert alert_staff("store payment", perm="payment.approve") == 0
        assert alert_staff("for us", perm="payment.approve", platform=True) == 1
    assert sent == [(777, "for us")]
    assert alert_staff("ours", perm="payment.approve") == 1


@pytest.mark.django_db(transaction=True)
def test_web_push_and_live_groups_stay_in_the_store(store, monkeypatch):
    from apps.notifications import live, webpush
    from apps.notifications.consumers import _payments_group_for

    assert async_to_sync(_payments_group_for)({"headers": [(b"host", HOST.encode())]}) == f"staff_payments_t{store.pk}"
    assert async_to_sync(_payments_group_for)({"headers": [(b"host", b"localhost")]}) == "staff_payments"
    assert async_to_sync(_payments_group_for)({"headers": [(b"host", b"unknown.example")]}) is None
    groups = []
    from channels import layers

    class Layer:
        async def group_send(self, group, msg):
            groups.append((group, msg["payload"].get("agency_review")))

    monkeypatch.setattr(layers, "get_channel_layer", lambda: Layer())
    with _in(store):
        live._send("receipt_uploaded", {})
    live._send("receipt_uploaded", {})
    assert groups[0] == (f"staff_payments_t{store.pk}", 0) and groups[1][0] == "staff_payments"
    queued = []
    monkeypatch.setattr(webpush, "enabled", lambda: True)
    monkeypatch.setattr(webpush, "_queue", lambda ids, payload: queued.append(ids) or len(ids))
    from apps.notifications.models import PushSubscription

    s = Staff(username="pushstaff", is_superadmin=True)
    s.set_password("x-Str0ng!"); s.save()
    PushSubscription.objects.create(staff=s, endpoint="https://push.test/1", p256dh="k", auth="a")
    with _in(store):
        assert webpush.push_to_staff("payment.view", title="t") == 0
    assert webpush.push_to_staff("payment.view", title="t") == 1
