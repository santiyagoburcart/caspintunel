"""v1.38 «فاکتور دستی»: mode A (already paid → approved payment + completed order on the ENTERED date, confirmed
by the staff member, optional service action), mode B (issued → customer pays with the normal checkout → Blu /
SMS auto-confirm → invoice paid + service action), the «دستی» tag everywhere, revenue date, permission, void."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.common.models import AuditLog
from apps.notifications.models import Notification
from apps.orders.models import ManualInvoice, Order, OrderStatus, OrderType
from apps.panel.models import Panel, Service
from apps.payments_sms.models import Payment, PaymentStatus
from apps.payments_sms.tests.test_blu import env, item, post, staff_client  # noqa: F401
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db(transaction=True)
JPG = b"\xff\xd8\xff\xe0" + b"0" * 64


@pytest.fixture
def world(monkeypatch):
    from apps.orders import services, tasks

    calls = []
    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda oid: calls.append(oid))
    monkeypatch.setattr(services, "check_account_name", lambda panel, name: None)
    panel = Panel.objects.create(name="p1", base_url="https://p.example", admin_username="u", admin_password_enc="x", is_active=True)
    plan = Plan.objects.create(name_fa="یک ماهه", name_en="One month", price=Decimal("150000"), data_limit=50 * 1024 ** 3,
                               duration_days=30, panel=panel)
    user = User.objects.create_user("cust1", "Str0ngPass!", name="Ali")
    svc = Service.objects.create(user=user, panel=panel, panel_username="ali1", current_plan=plan)
    return {"plan": plan, "user": user, "svc": svc, "fulfil": calls, "boss": staff_client("super", "boss")}


def U(w):
    return f"/api/v1/admin/users/{w['user'].id}/manual-invoices/"


def customer(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def test_mode_a_paid_custom_item_on_the_entered_date(world, env):  # noqa: F811
    boss = world["boss"]
    paid_at = timezone.now() - timedelta(days=10)
    r = boss.post(U(world), {"mode": "paid", "title": "تمدید دستی ماه قبل", "volume_gb": 40, "days": 30, "amount": "250000",
                             "paid_at": paid_at.isoformat(), "method": "cash", "receipt_ref": "۱۲۳۴۵۶",
                             "receipt_image": SimpleUploadedFile("r.jpg", JPG, content_type="image/jpeg"), "note": "paid in person"},
                  format="multipart")
    assert r.status_code == 201, r.content
    inv = ManualInvoice.objects.get()
    p = Payment.objects.get(order__manual_invoice=inv)
    assert inv.status == ManualInvoice.PAID and inv.mode == "paid" and inv.created_by.username == "boss"
    assert p.status == PaymentStatus.APPROVED and p.method == "cash" and p.bank_card_id is None
    assert p.confirmed_by == "admin" and p.confirmed_by_staff.username == "boss"
    assert abs((p.confirmed_at - paid_at).total_seconds()) < 2 and p.receipt_ref == "123456" and p.receipt_sha256
    assert p.order.status == OrderStatus.COMPLETED and p.order.type == OrderType.MANUAL and p.order.amount_unique_lock is None
    assert world["fulfil"] == []                                   # no service action → nothing on PasarGuard
    assert r.json()["tx_number"] == p.tx_number                    # same TX numbering
    # revenue on the ENTERED date, not today
    day = paid_at.date().isoformat()
    acc = boss.get(f"/api/v1/admin/accounting/?from={day}&to={day}").json()
    assert Decimal(str(acc["revenue"])) == Decimal("250000") and acc["manual"]["count"] == 1
    today = timezone.now().date().isoformat()
    assert Decimal(str(boss.get(f"/api/v1/admin/accounting/?from={today}&to={today}").json()["revenue"])) == 0
    # the «دستی» tag everywhere
    tx = boss.get(f"/api/v1/admin/transactions/{p.id}/").json()
    assert tx["manual"]["number"] == inv.number and tx["manual"]["created_by"] == "boss"
    assert boss.get("/api/v1/admin/transactions/?manual=1").json()["results"][0]["id"] == p.id
    csv = boss.get("/api/v1/admin/transactions/?export=csv&lang=en").content.decode("utf-8")
    assert f"manual {inv.number}" in csv
    assert boss.get(f"/api/v1/admin/users/{world['user'].id}/orders/").json()[0]["manual"]["number"] == inv.number
    assert customer(world["user"]).get("/api/v1/orders/").json()["results"][0]["manual"]["number"] == inv.number
    assert AuditLog.objects.filter(action="manual_invoice.created_paid", staff_label="boss").exists()
    assert not Notification.objects.filter(target_user=world["user"]).exists()     # staff entered it: no "confirmed" message
    # a second one with the same tracking number warns
    r2 = boss.post(U(world), {"mode": "paid", "title": "x", "amount": "1000", "method": "other", "receipt_ref": "123456"},
                   format="multipart")
    assert r2.status_code == 201 and r2.json()["warnings"][0]["kind"] == "duplicate_ref"


def test_mode_a_with_renewal_runs_the_normal_fulfilment(world, env):  # noqa: F811
    r = world["boss"].post(U(world), {"mode": "paid", "plan": world["plan"].id, "amount": "150000", "method": "card",
                                      "service_action": "renew", "service": world["svc"].id}, format="multipart")
    assert r.status_code == 201, r.content
    o = Order.objects.get(manual_invoice__isnull=False)
    assert o.type == OrderType.RENEW and o.service_id == world["svc"].id and o.status == OrderStatus.PAID
    assert world["fulfil"] == [o.id]
    # a service of another customer / no plan → refused
    other = User.objects.create_user("cust2", "Str0ngPass!")
    s2 = Service.objects.create(user=other, panel=world["plan"].panel, panel_username="zz", current_plan=world["plan"])
    bad = world["boss"].post(U(world), {"mode": "paid", "plan": world["plan"].id, "amount": "1", "service_action": "renew",
                                        "service": s2.id}, format="multipart")
    assert bad.status_code == 400 and bad.json()["field"] == "service"
    assert world["boss"].post(U(world), {"mode": "paid", "title": "t", "amount": "1", "service_action": "new"},
                              format="multipart").json()["field"] == "plan"


def test_mode_b_issue_pay_by_blu_and_new_service(world, env):  # noqa: F811
    boss = world["boss"]
    due = timezone.now() + timedelta(days=3)
    r = boss.post(U(world), {"mode": "issued", "plan": world["plan"].id, "amount": "180000", "due_at": due.isoformat(),
                             "service_action": "new", "account_name": "ali-new"}, format="json")
    assert r.status_code == 201, r.content
    inv = ManualInvoice.objects.get()
    assert inv.status == "open" and Notification.objects.filter(target_user=world["user"], link="/history").exists()
    c = customer(world["user"])
    lst = c.get("/api/v1/orders/manual-invoices/").json()
    assert lst["open"] == 1 and lst["results"][0]["number"] == inv.number
    co = c.post(f"/api/v1/orders/manual-invoices/{inv.id}/pay/", {}, format="json")
    assert co.status_code == 201, co.content
    order = Order.objects.get(pk=co.json()["order"]["id"])
    assert order.manual_invoice_id == inv.id and order.type == OrderType.NEW and order.amount == Decimal("180000")
    assert order.amount_unique > order.amount and order.amount_unique_lock == order.amount_unique   # a real reservation
    assert c.post(f"/api/v1/orders/manual-invoices/{inv.id}/pay/", {}, format="json").json()["order"]["id"] == order.id  # reused
    assert post([item(int(order.amount_unique))]).status_code in (200, 201, 202)
    inv.refresh_from_db(); order.refresh_from_db()
    p = Payment.objects.get(order=order)
    assert p.status == PaymentStatus.APPROVED and p.method == "blu_auto"
    assert inv.status == "paid" and inv.order_id == order.id and inv.paid_at and order.status == OrderStatus.PAID
    assert world["fulfil"] == [order.id] and order.amount_unique_lock is None
    assert c.post(f"/api/v1/orders/manual-invoices/{inv.id}/pay/", {}, format="json").status_code == 400
    # void → the invoice is open again; restore → paid
    from apps.accounts.models import Staff
    from apps.payments_sms import voiding

    st = Staff.objects.get(username="boss")
    voiding.void_payment(p.id, staff=st, reason="test", service_action="keep")
    inv.refresh_from_db(); assert inv.status == "open"
    voiding.restore_payment(p.id, staff=st)
    inv.refresh_from_db(); assert inv.status == "paid"


def test_permission_and_cancel(world):
    viewer = staff_client(["payment.view"], "viewer")
    assert viewer.get(U(world)).status_code == 200
    assert viewer.post(U(world), {"mode": "issued", "title": "x", "amount": "1000"}, format="json").status_code == 403
    assert viewer.get(U(world) + "options/").status_code == 403
    maker = staff_client(["payments.manual_invoice", "payment.view"], "maker")
    opts = maker.get(U(world) + "options/").json()
    assert opts["services"][0]["name"] == "ali1" and opts["plans"][0]["id"] == world["plan"].id
    r = maker.post(U(world), {"mode": "issued", "title": "x", "amount": "1000"}, format="json")
    assert r.status_code == 201
    assert maker.post(f"/api/v1/admin/manual-invoices/{r.json()['id']}/cancel/", {"reason": "dup"}, format="json").status_code == 200
    assert ManualInvoice.objects.get().status == "cancelled"
    assert maker.post(U(world), {"mode": "issued", "amount": "1000"}, format="json").json()["field"] == "title"
