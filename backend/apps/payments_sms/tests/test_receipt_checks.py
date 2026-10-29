"""Approval-queue warnings (v1.30.1, incident 2026-10-29): receipt amount ≠ unique amount,
a recent SMS-approved payment of the same customer / service, the same receipt image
(sha256) or bank document number on another payment — each with the linked payment."""
import importlib
import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Staff, User
from apps.common.models import AuditLog
from apps.orders.models import OrderType
from apps.orders.services import create_order
from apps.panel.models import Panel, Service, ServiceStatus
from apps.payments_sms.checks import normalize_ref, parse_amount, payment_warnings
from apps.payments_sms.models import ConfirmedBy, Payment, PaymentMethod, PaymentStatus
from apps.payments_sms.services import submit_receipt
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db
GB = 1024 ** 3


def _png(color=(0, 0, 0)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buf, format="PNG")
    return SimpleUploadedFile("r.png", buf.getvalue(), content_type="image/png")


@pytest.fixture
def setup():
    panel = Panel.objects.create(name="P", base_url="https://p.test", admin_username="a", admin_password_enc="p")
    plan = Plan.objects.create(panel=panel, name_fa="طلایی", price=Decimal("470000"), data_limit=100 * GB,
                               duration_days=31)
    user = User.objects.create_user("mojtaba", "Str0ngPass!")
    svc = Service.objects.create(user=user, panel=panel, panel_username="mojtaba_acc", current_plan=plan,
                                 status=ServiceStatus.ACTIVE, subscription_url="https://p.test/sub/x",
                                 data_limit=50 * GB, data_used=49 * GB,
                                 expire_at=timezone.now() + timedelta(days=20), source="import")
    return plan, user, svc


@pytest.fixture
def boss():
    s = Staff(username="boss", is_superadmin=True)
    s.set_password("Str0ngPass!")
    s.save()
    from apps.adminpanel.tokens import issue_tokens

    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


def _new_order(user, plan, name):
    return create_order(user=user, plan_id=plan.id, requested_account_name=name)


def _sms_paid(user, plan, svc=None, when=None):
    o = create_order(user=user, plan_id=plan.id, order_type=OrderType.RENEW, service_id=svc.id) if svc \
        else _new_order(user, plan, "sms-acc")
    return Payment.objects.create(order=o, method=PaymentMethod.SMS_AUTO, amount=o.amount_unique,
                                  status=PaymentStatus.APPROVED, confirmed_by=ConfirmedBy.SYSTEM,
                                  confirmed_at=when or timezone.now())


def _kinds(p):
    return {w["kind"]: w for w in payment_warnings(p)}


def test_helpers_normalize_ref_and_amount_units():
    assert normalize_ref("۱۴۰۵۶۶۰۵ 138398") == "14056605138398"
    assert parse_amount("4,711,490", "rial") == Decimal("471149")
    assert parse_amount("۴۷۱۱۴۹", "toman") == Decimal("471149")
    assert parse_amount("", "toman") is None
    with pytest.raises(ValueError):
        parse_amount("4711491", "rial")


def test_upload_stores_the_image_hash_and_the_tracking_number(setup):
    plan, user, _ = setup
    o = _new_order(user, plan, "a1")
    c = APIClient()
    c.force_authenticate(user)
    r = c.post("/api/v1/payments/receipt/", {"order": o.id, "receipt_image": _png(), "receipt_ref": "۱۴۰۵-۶۶۰۵"},
               format="multipart")
    assert r.status_code == 201, r.data
    p = Payment.objects.get(order=o)
    assert len(p.receipt_sha256) == 64 and p.receipt_ref == "14056605"


def test_same_receipt_image_on_another_payment_is_flagged_with_the_link(setup):
    plan, user, _ = setup
    first = submit_receipt(order=_new_order(user, plan, "a1"), image=_png((9, 9, 9)), user=user)
    other = submit_receipt(order=_new_order(user, plan, "a2"), image=_png((1, 2, 3)), user=user)
    second = submit_receipt(order=_new_order(user, plan, "a3"), image=_png((9, 9, 9)), user=user)
    w = _kinds(second)["duplicate_image"]
    assert [x["id"] for x in w["payments"]] == [first.id]
    assert w["payments"][0]["tx"] == first.tx_number and w["payments"][0]["order_id"] == first.order_id
    assert "duplicate_image" not in _kinds(other)
    Payment.objects.filter(pk=first.pk).update(voided_at=timezone.now())      # a voided one still counts
    assert _kinds(second)["duplicate_image"]["payments"][0]["voided"] is True


def test_same_bank_document_number_is_flagged(setup):
    plan, user, _ = setup
    first = submit_receipt(order=_new_order(user, plan, "a1"), image=_png((1, 1, 1)), user=user,
                           receipt_ref="14056605138398")
    second = submit_receipt(order=_new_order(user, plan, "a2"), image=_png((2, 2, 2)), user=user,
                            receipt_ref="۱۴۰۵۶۶۰۵۱۳۸۳۹۸")
    w = _kinds(second)["duplicate_ref"]
    assert w["ref"] == "14056605138398" and w["payments"][0]["id"] == first.id


def test_recent_sms_payment_of_the_same_customer_and_service(setup):
    plan, user, svc = setup
    sms = _sms_paid(user, plan, svc)
    sms.order.status = "completed"
    sms.order.save()
    from apps.orders.models import ScheduledRenewal

    ScheduledRenewal.objects.create(service=svc, plan=plan, order=sms.order, renewal_mode="reset")
    # a second renewal invoice made before the guard (old data): receipt under review
    from apps.orders.models import Order

    o2 = Order.objects.create(user=user, plan=plan, service=svc, type=OrderType.RENEW, amount=plan.price,
                              original_amount=plan.price, amount_unique=Decimal("470282"), status="pending_payment",
                              unique_expire_at=timezone.now() + timedelta(minutes=30))
    p2 = submit_receipt(order=o2, image=_png((5, 5, 5)), user=user)
    k = _kinds(p2)
    assert k["recent_sms"]["payments"][0]["id"] == sms.id and k["recent_sms"]["payments"][0]["same_service"] is True
    assert k["renewal_waiting"]["order_id"] == sms.order_id


def test_old_sms_payment_is_not_recent(setup):
    plan, user, _ = setup
    _sms_paid(user, plan, when=timezone.now() - timedelta(days=3))
    p = submit_receipt(order=_new_order(user, plan, "a9"), image=_png((7, 7, 7)), user=user)
    assert "recent_sms" not in _kinds(p)


def test_staff_record_receipt_amount_and_ref_then_queue_shows_warnings(setup, boss):
    plan, user, _ = setup
    o = _new_order(user, plan, "a1")
    p = submit_receipt(order=o, image=_png((3, 3, 3)), user=user)
    r = boss.post(f"/api/v1/admin/payments/{p.id}/receipt-info/",
                  {"receipt_amount": "4,711,490", "unit": "rial", "receipt_ref": "14056605138398"}, format="json")
    assert r.status_code == 200, r.data
    p.refresh_from_db()
    assert p.receipt_amount == Decimal("471149") and p.receipt_ref == "14056605138398"
    assert AuditLog.objects.filter(action="payment.receipt_info", target_id=p.id).exists()
    mismatch = next(w for w in r.data["warnings"] if w["kind"] == "amount_mismatch")
    assert Decimal(mismatch["invoice_amount"]) == o.amount_unique
    assert Decimal(mismatch["receipt_amount"]) == Decimal("471149")
    # equal amount → no mismatch
    r = boss.post(f"/api/v1/admin/payments/{p.id}/receipt-info/",
                  {"receipt_amount": str(o.amount_unique), "unit": "toman"}, format="json")
    assert not any(w["kind"] == "amount_mismatch" for w in r.data["warnings"])
    # a Rial amount that can't be tomans is refused
    r = boss.post(f"/api/v1/admin/payments/{p.id}/receipt-info/", {"receipt_amount": "4711491", "unit": "rial"},
                  format="json")
    assert r.status_code == 400
    q = boss.get("/api/v1/admin/payments/pending/").data["results"]
    row = next(x for x in q if x["id"] == p.id)
    assert row["tx"] == p.tx_number and "warnings" in row and row["receipt_ref"] == "14056605138398"


def test_receipt_info_needs_payment_approve(setup):
    plan, user, _ = setup
    p = submit_receipt(order=_new_order(user, plan, "a1"), image=_png(), user=user)
    s = Staff(username="viewer")
    s.set_password("Str0ngPass!")
    s.save()
    from apps.adminpanel.tokens import issue_tokens

    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    assert c.post(f"/api/v1/admin/payments/{p.id}/receipt-info/", {"receipt_ref": "1"}, format="json").status_code == 403


def test_migration_backfills_hashes_and_skips_missing_files(setup):
    from django.apps import apps as registry

    plan, user, _ = setup
    p = submit_receipt(order=_new_order(user, plan, "a1"), image=_png((4, 4, 4)), user=user)
    good = p.receipt_sha256
    Payment.objects.filter(pk=p.pk).update(receipt_sha256="")
    gone = submit_receipt(order=_new_order(user, plan, "a2"), image=_png((6, 6, 6)), user=user)
    Payment.objects.filter(pk=gone.pk).update(receipt_sha256="", receipt_image="receipts/missing.png")
    mig = importlib.import_module("apps.payments_sms.migrations.0010_payment_receipt_checks")
    mig.backfill_hashes(registry, None)
    assert Payment.objects.get(pk=p.pk).receipt_sha256 == good
    assert Payment.objects.get(pk=gone.pk).receipt_sha256 == ""
