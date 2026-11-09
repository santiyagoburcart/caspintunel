"""manage.py watch_payments (v1.48): follows the next N payments of OUR store; a deposit that does not match → staff alert."""
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import User
from apps.common.models import AuditLog
from apps.orders.models import Order, OrderStatus, OrderType
from apps.payments_sms.management.commands import watch_payments as cmd
from apps.payments_sms.models import BluStatus, BluTransaction, Payment, PaymentMethod, PaymentStatus, SmsMessage
from apps.plans.models import Plan
from apps.tenancy import context
from apps.tenancy.models import Tenant

pytestmark = pytest.mark.django_db


def _order(n):
    u = User.objects.create_user(f"w{n}-{User.objects.count()}", "Str0ngPass!")
    plan = Plan.objects.create(name_fa="p", price=Decimal(100000), data_limit=1024 ** 3, duration_days=30)
    return Order.objects.create(user=u, plan=plan, type=OrderType.NEW, status=OrderStatus.PAID,
                                amount=Decimal(100000), amount_unique=Decimal(100000 + n),
                                unique_expire_at=timezone.now())


def _receipt(order, status):
    p = Payment.objects.create(order=order, method=PaymentMethod.CARD_MANUAL, amount=order.amount_unique, status=status)
    AuditLog.objects.create(action="payment.receipt_uploaded", target_type="Payment", target_id=p.pk)
    return p


@pytest.fixture
def alerts(monkeypatch):
    sent = []
    monkeypatch.setattr("apps.common.staff_alert.alert_staff", lambda text, **kw: sent.append((text, kw)) or 1)
    return sent


def _arrive(monkeypatch, make):
    """Payments arrive while the command sleeps; a second sleep means it waited for more than there is."""
    calls = []

    def sleep(_):
        calls.append(1)
        if len(calls) > 1:
            raise AssertionError("watch_payments kept waiting")
        make()

    monkeypatch.setattr(cmd.time, "sleep", sleep)


def test_matched_sms_approved_receipt_and_unmatched_blu(monkeypatch, alerts):
    o1, o2 = _order(1), _order(2)

    def make():
        SmsMessage.objects.create(raw_text="واریز", parsed_amount=o1.amount_unique, matched_order=o1)
        _receipt(o1, PaymentStatus.APPROVED)                    # the same payment as the SMS: counted once
        BluTransaction.objects.create(bank_id="b-1", amount_irr=1234560, amount_toman=Decimal(123456),
                                      occurred_at=timezone.now(), status=BluStatus.UNMATCHED, match_note="no order")
        BluTransaction.objects.create(bank_id="b-2", amount_irr=10, amount_toman=Decimal(1),
                                      occurred_at=timezone.now(), status=BluStatus.IGNORED)      # not a deposit
        _receipt(o2, PaymentStatus.APPROVED)

    _arrive(monkeypatch, make)
    with pytest.raises(SystemExit) as exit_:
        call_command("watch_payments", count=3, grace=0, receipt_wait=0)
    assert exit_.value.code == 2
    fails = [t for t, kw in alerts if "تطبیق داده نشد" in t]
    assert len(fails) == 1 and "Blu #" in fails[0] and "no order" in fails[0]
    summary = alerts[-1][0]
    assert "2 matched, 1 failed" in summary and f"order #{o1.pk}" in summary and f"order #{o2.pk}" in summary
    assert alerts[-1][1]["perm"] == "payment.view" and not alerts[-1][1].get("platform")


def test_all_matched_is_a_quiet_summary_and_store_payments_are_not_ours(monkeypatch, alerts):
    o1, o2, o3 = _order(1), _order(2), _order(3)
    store = Tenant.objects.create(slug="sw", name="Store W", status="active", reseller_username="swadmin")

    def make():
        with context.tenant_context(store.pk):                  # a store's SMS — never in our watch / alerts
            SmsMessage.objects.create(raw_text="واریز", parsed_amount=Decimal(9))
        SmsMessage.objects.create(raw_text="واریز", parsed_amount=o1.amount_unique, matched_order=o1)
        BluTransaction.objects.create(bank_id="b-3", amount_irr=1000020, amount_toman=o2.amount_unique,
                                      occurred_at=timezone.now(), status=BluStatus.MATCHED, matched_order=o2)
        _receipt(o3, PaymentStatus.REJECTED)                    # a staff decision, not a match failure

    _arrive(monkeypatch, make)
    call_command("watch_payments", count=3, grace=0, receipt_wait=0)
    assert len(alerts) == 1 and alerts[0][1]["silent"] is True and "3 matched, 0 failed" in alerts[0][0]
