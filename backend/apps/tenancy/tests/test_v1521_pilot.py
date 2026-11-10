"""v1.52.1 — two gaps found while preparing the Phase 9 pilot (docs/pilot-fa.md).

1. A new store gets a copy of OUR active ticket topics (no staff scopes), editable by the reseller; the store dashboard warns
   when the store has no active topic.
2. «ساخت ناموفق» in a store: listed with PasarGuard's error in the store's panel (payment.view) and retried there
   (payment.approve) with an optional new account name — and on our «فروشگاه» card (agency.manage). The retry is the SAME paid
   order (no new order / payment); both sides are alerted; our failed orders never show in a store and vice versa.
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Permission, Role, Staff, User
from apps.agency.models import PanelAdmin
from apps.common.models import AuditLog
from apps.orders.models import Order, OrderStatus, OrderType
from apps.panel.models import Panel
from apps.payments_sms.models import Payment, PaymentStatus
from apps.plans.models import Plan
from apps.tenancy import context, stores
from apps.tenancy import staff as S
from apps.tenancy.models import Tenant, TenantDomain
from apps.tenancy.tests.test_phase8 import _boss, _client
from apps.tickets.models import TicketTopic

pytestmark = pytest.mark.django_db
HOST = "shop-p9.example"
AGENCY = "/api/v1/admin/agency/panel-admins/p9admin/store/failed-orders/"
STORE_API = "/api/v1/admin/orders/provision-failed/"


@pytest.fixture
def codes(_default_tenant):
    for c in sorted(S.STORE_CODES | {"agency.manage"}):
        Permission.objects.get_or_create(code=c, defaults={"name": c})


@pytest.fixture
def store(codes):
    t = Tenant.objects.create(slug="s9", name="Store Nine", status="active", reseller_username="p9admin",
                              permission_ceiling=list(S.DEFAULT_CEILING))
    TenantDomain.objects.create(tenant=t, host=HOST, state="active")
    return t


@pytest.fixture
def panel(_default_tenant):
    return Panel.objects.create(name="P9", base_url="https://panel.test", admin_username="a", admin_password_enc="p",
                                is_active=True)


@pytest.fixture
def free_names(monkeypatch):
    from apps.orders import services

    monkeypatch.setattr(services, "check_account_name", lambda panel, name: None)


@pytest.fixture
def queued(monkeypatch):
    """fulfill_order.delay stub: records (order id, the store it was queued in)."""
    from apps.orders import tasks

    out = []
    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda oid: out.append((oid, context.store_id())))
    return out


def _failed_order(panel, name, *, error="Username can only contain alphanumeric characters"):
    """A paid NEW order PasarGuard refused — in the CURRENT tenant context."""
    u = User.objects.create_user(f"{name}_u", "Str0ngPass!")
    plan = Plan.objects.create(panel=panel, name_fa=f"پلن {name}", name_en=f"Plan {name}", price=Decimal("100000"),
                               data_limit=10 * 1024 ** 3, duration_days=30)
    o = Order.objects.create(user=u, plan=plan, type=OrderType.NEW, status=OrderStatus.PAID, amount=100000,
                             amount_unique=100123, requested_account_name=name,
                             unique_expire_at=timezone.now() + timezone.timedelta(minutes=10),
                             provision_error=error, provision_failed_at=timezone.now())
    Payment.objects.create(order=o, amount=100123, status=PaymentStatus.APPROVED, confirmed_at=timezone.now())
    return o


# ------------------------------------------------------------------ 1. ticket topics
def test_a_new_store_gets_a_copy_of_our_active_topics_without_staff_scopes(codes):
    PanelAdmin.objects.create(username="p9new")
    TicketTopic.objects.all().delete()                                       # the seeded topics (migration 0002)
    ours = TicketTopic.objects.create(name_fa="فنی ما", name_en="Our tech", requires_active_service=False, sort_order=5)
    ours.staff.add(Staff.objects.create(username="our-scoped"))
    TicketTopic.objects.create(name_fa="غیرفعال", name_en="Inactive", is_active=False)
    t = stores.enable("p9new", name="New Nine")
    with context.tenant_context(t.pk):
        copies = list(TicketTopic.objects.all())
        assert [(c.name_fa, c.requires_active_service, c.is_active) for c in copies] == [("فنی ما", False, True)]
        assert copies[0].pk != ours.pk and copies[0].staff.count() == 0
        copies[0].name_fa = "فنی فروشگاه"                                  # the reseller edits its own copy
        copies[0].save()
    ours.refresh_from_db()
    assert ours.name_fa == "فنی ما"
    assert AuditLog.objects.filter(action="store.enabled", detail__topics_copied=1).exists()


def test_without_our_topics_the_starter_list_is_used(codes):
    PanelAdmin.objects.create(username="p9bare")
    TicketTopic.objects.all().delete()
    t = stores.enable("p9bare")
    with context.tenant_context(t.pk):
        assert TicketTopic.objects.filter(is_active=True).count() == 5
    assert not TicketTopic.objects.exists()                                  # ours untouched (still none)


def test_store_dashboard_warns_without_an_active_topic(store, panel):
    owner, _ = S.ensure_owner(store, "p9owner")
    c = _client(owner, HOST)
    d = c.get("/api/v1/admin/dashboard/").json()
    assert d["ticket_topics_active"] == 0 and d["failed_orders"] == 0
    with context.tenant_context(store.pk):
        TicketTopic.objects.create(name_fa="t", name_en="t")
    assert c.get("/api/v1/admin/dashboard/").json()["ticket_topics_active"] == 1


# ------------------------------------------------------------------ 2. failed store orders
def test_store_panel_lists_and_retries_its_failed_orders_without_charging_again(
        store, panel, free_names, queued, django_capture_on_commit_callbacks):
    ours = _failed_order(panel, "our_fail")
    with context.tenant_context(store.pk):
        o = _failed_order(panel, "store_fail")
    owner, _ = S.ensure_owner(store, "p9owner")
    c = _client(owner, HOST)
    rows = c.get(STORE_API).json()["results"]
    assert [r["order"] for r in rows] == [o.pk]                             # never our failed order
    assert "alphanumeric" in rows[0]["error"] and rows[0]["account_name"] == "store_fail" and rows[0]["name_editable"]
    assert c.get("/api/v1/admin/dashboard/").json()["failed_orders"] == 1
    assert c.post(f"{STORE_API}{ours.pk}/retry/", {}, format="json").status_code == 404   # ours is not reachable
    r = c.post(f"{STORE_API}{o.pk}/retry/", {"account_name": "bad name"}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "account_name" and r.json()["suggestion"] == "bad_name"
    with context.tenant_context(store.pk):
        before = (Order.objects.count(), Payment.objects.count())
    with django_capture_on_commit_callbacks(execute=True):
        r = c.post(f"{STORE_API}{o.pk}/retry/", {"account_name": "store_fixed"}, format="json")
    assert r.status_code == 200, r.content
    assert queued == [(o.pk, store.pk)]                                      # queued inside the store
    with context.tenant_context(store.pk):
        assert (Order.objects.count(), Payment.objects.count()) == before   # same order, same payment — no new charge
        o.refresh_from_db()
        assert o.provision_failed_at is None and o.requested_account_name == "store_fixed" and o.status == OrderStatus.PAID
    assert c.get(STORE_API).json()["results"] == []
    assert c.post(f"{STORE_API}{o.pk}/retry/", {}, format="json").status_code == 404     # nothing to retry twice
    ours.refresh_from_db()
    assert ours.provision_failed_at is not None


def test_store_staff_need_payment_approve_to_retry(store, panel):
    with context.tenant_context(store.pk):
        o = _failed_order(panel, "perm_fail")
    role = Role.objects.create(tenant=store, name="viewer")
    role.permissions.set(Permission.objects.filter(code="payment.view"))
    viewer = Staff.objects.create(username="p9viewer", tenant=store, role=role)
    c = _client(viewer, HOST)
    assert [r["order"] for r in c.get(STORE_API).json()["results"]] == [o.pk]
    assert c.post(f"{STORE_API}{o.pk}/retry/", {}, format="json").status_code == 403


def test_our_staff_see_and_retry_a_stores_failed_orders_on_its_card(
        store, panel, free_names, queued, django_capture_on_commit_callbacks):
    _failed_order(panel, "our_fail2")
    with context.tenant_context(store.pk):
        o = _failed_order(panel, "store_fail2")
    boss = _boss()
    assert boss.get("/api/v1/admin/agency/panel-admins/p9admin/store/").json()["store"]["failed_orders"] == 1
    rows = boss.get(AGENCY).json()["results"]
    assert [r["order"] for r in rows] == [o.pk]
    with django_capture_on_commit_callbacks(execute=True):
        r = boss.post(f"{AGENCY}{o.pk}/retry/", {}, format="json")
    assert r.status_code == 200, r.content
    assert queued == [(o.pk, store.pk)]
    assert AuditLog.objects.filter(action="order.provision_retry", target_id=o.pk).exists()
    assert boss.get(AGENCY).json()["results"] == []
    # the store's domain never answers our «فروشگاه» endpoints
    owner, _ = S.ensure_owner(store, "p9owner")
    assert _client(owner, HOST).get(AGENCY).status_code in (403, 404)


def test_a_store_failure_alerts_the_store_and_us(store, panel, monkeypatch):
    from apps.common import staff_alert
    from apps.orders import tasks
    from apps.panel.exceptions import PanelValidationError

    alerts = []
    monkeypatch.setattr(staff_alert, "alert_staff", lambda text, **kw: alerts.append((text, kw)) or 1)
    with context.tenant_context(store.pk):
        o = _failed_order(panel, "alert_fail")
        o.provision_failed_at, o.provision_error = None, ""
        o.save()
        tasks._provision_failed(o, PanelValidationError("422", status_code=422, body='{"detail": "bad name"}'))
    assert len(alerts) == 2
    (store_text, store_kw), (our_text, our_kw) = alerts
    assert not store_kw.get("platform") and "پنل فروشگاه" in store_text and "دوباره" in store_text
    assert our_kw["platform"] is True and "Store Nine" in our_text and "سفارش‌های ناموفق" in our_text
    # our own store: one alert, as before
    alerts.clear()
    o2 = _failed_order(panel, "our_alert")
    o2.provision_failed_at = None
    o2.save()
    tasks._provision_failed(o2, PanelValidationError("422", status_code=422, body='{"detail": "bad"}'))
    assert len(alerts) == 1 and not alerts[0][1].get("platform") and "Transactions" in alerts[0][0]
