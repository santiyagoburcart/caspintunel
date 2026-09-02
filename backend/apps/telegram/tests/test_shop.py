from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.panel.models import Panel, Service, ServiceStatus
from apps.plans.models import Plan, PlanType
from apps.telegram.shop import buy_new, plan_label, renew, service_summary

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user("u", "Str0ngPass!", telegram_id=9)


@pytest.fixture
def plan():
    return Plan.objects.create(name_fa="۳۰روزه", price=Decimal("120000"),
                               data_limit=50 * 1024**3, duration_days=30, group_ids=[6])


def test_buy_new_creates_bot_sourced_order(user, plan):
    order = buy_new(user, plan, account_name="tguser1")
    assert order.source == "bot"
    assert order.type == "new"
    assert order.amount == Decimal("120000")
    assert order.requested_account_name == "tguser1"


def test_renew_creates_renew_order(user, plan):
    panel = Panel.objects.create(name="P", base_url="https://x", admin_username="a", admin_password_enc="p")
    svc = Service.objects.create(user=user, panel=panel, panel_username="tguser1",
                                 current_plan=plan, status=ServiceStatus.EXPIRED)
    order = renew(user, svc, plan)
    assert order.type == "renew"
    assert order.service_id == svc.id
    assert order.source == "bot"


def test_plan_label_and_service_summary(user, plan):
    label = plan_label(plan)
    assert "۳۰روزه" in label and "50 گیگ" in label and "تومان" in label

    panel = Panel.objects.create(name="P", base_url="https://x", admin_username="a", admin_password_enc="p")
    svc = Service.objects.create(user=user, panel=panel, panel_username="x1", current_plan=plan,
                                 status=ServiceStatus.ACTIVE, data_limit=50 * 1024**3,
                                 data_used=10 * 1024**3)
    summary = service_summary(svc)
    assert "x1" in summary and "فعال" in summary and "10 از 50" in summary


def test_custom_volume_label(user):
    cv = Plan.objects.create(name_fa="حجمی", type=PlanType.CUSTOM_VOLUME, price=Decimal("0"),
                             price_per_gb=Decimal("2500"), min_gb=5, max_gb=100)
    assert "حجمی" in plan_label(cv)


# --- bot receipt upload ------------------------------------------------
def test_submit_bot_receipt_creates_pending_payment_with_a_real_file(user, plan):
    import io
    import os

    from PIL import Image

    from apps.orders.models import OrderStatus
    from apps.payments_sms.models import PaymentStatus
    from apps.telegram.shop import order_awaiting_receipt, submit_bot_receipt

    order = buy_new(user, plan, account_name="tgacc")
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert order_awaiting_receipt(user).id == order.id

    buf = io.BytesIO()
    Image.new("RGB", (200, 120), (10, 90, 200)).save(buf, format="JPEG")
    payment = submit_bot_receipt(user, order, buf.getvalue())

    assert payment.status == PaymentStatus.PENDING
    assert payment.method == "card_manual"
    assert payment.amount == order.amount_unique
    assert payment.receipt_image.name.endswith(".jpg")
    assert os.path.exists(payment.receipt_image.path)
    assert payment.receipt_image.storage.exists(payment.receipt_image.name)


def test_submit_bot_receipt_rejects_non_image_bytes(user, plan):
    from apps.payments_sms.services import PaymentError
    from apps.telegram.shop import submit_bot_receipt

    order = buy_new(user, plan, account_name="tgacc2")
    with pytest.raises(PaymentError):
        submit_bot_receipt(user, order, b"not an image at all")
    with pytest.raises(PaymentError):
        submit_bot_receipt(user, order, b"")


def test_service_summary_shows_waiting_for_connection(user, plan):
    panel = Panel.objects.create(name="P", base_url="https://x", admin_username="a",
                                 admin_password_enc="p")
    svc = Service.objects.create(
        user=user, panel=panel, panel_username="s-1", current_plan=plan,
        status=ServiceStatus.ON_HOLD, on_hold_duration=30 * 86400, online_at=None,
        subscription_url="https://x/s/",
    )
    text = service_summary(svc)
    assert "با اولین اتصال فعال می‌شود" in text
    assert "30 روز" in text
