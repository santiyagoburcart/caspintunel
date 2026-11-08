"""Multi-tenant Phase 4 (v1.46): catalog + PasarGuard per store.

* Celery tasks run for the store they were queued from (tenancy/celery_ctx.py) — a real worker thread on the memory broker;
  the periodic jobs that touch customer data loop over every store.
* A store's new account is created with our token, then set_owner → the reseller's PasarGuard admin, read back.
* Quota guard (tenancy/quota.py): before the order, again before the account is made, manual invoices; warnings at 20 / 10 %.
* Store plans (tenancy/catalog.py): agency panel only, the reseller role's groups, no unlimited plan for a limited reseller.
"""
import json
from decimal import Decimal

import pytest
import responses
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.agency.models import AgencyNotice, PanelAdmin
from apps.orders.models import Order, OrderStatus, OrderType
from apps.panel.exceptions import PanelError
from apps.panel.models import Panel, Service, ServiceStatus
from apps.payments_sms.tests.test_blu import staff_client
from apps.plans.models import Plan
from apps.tenancy import context, quota
from apps.tenancy.models import Tenant, TenantDomain

pytestmark = pytest.mark.django_db
GB = 1024 ** 3
BASE = "https://panel.test"
HOST = "shop-p4.example"


@pytest.fixture
def panel(_default_tenant):
    return Panel.objects.create(name="P", base_url=BASE, admin_username="adm", admin_password_enc="pw", is_active=True)


@pytest.fixture
def reseller(db):
    return PanelAdmin.objects.create(username="seller1", has_data_limit=True, admin_limit_bytes=100 * GB,
                                     admin_remaining=60 * GB, total_user_used=40 * GB)


@pytest.fixture
def store(panel, reseller):
    t = Tenant.objects.create(slug="seller1", name="Store P4", status="active", reseller_username="seller1")
    TenantDomain.objects.create(tenant=t, host=HOST, state="active")
    return t


@pytest.fixture
def alerts(monkeypatch):
    out = []
    from apps.common import staff_alert

    monkeypatch.setattr(staff_alert, "alert_staff", lambda text, **kw: out.append(text) or 1)
    return out


def _plan(panel, gb=10, **kw):
    return Plan.objects.create(panel=panel, name_fa=f"p{gb}", price=Decimal("100000"), duration_days=30,
                               data_limit=gb * GB if gb else None, **kw)


def _soon():
    from django.utils import timezone

    return timezone.now() + timezone.timedelta(minutes=10)


def _in(store):
    return context.tenant_context(store.pk)


# ------------------------------------------------------------------ Celery carries the store
def test_publish_hook_stamps_the_explicit_tenant_and_never_overwrites(store):
    from apps.tenancy import celery_ctx

    h = {}
    with _in(store):
        celery_ctx.stamp_tenant(headers=h)
    assert h[celery_ctx.HEADER] == store.pk
    keep = {celery_ctx.HEADER: 99}
    with _in(store):
        celery_ctx.stamp_tenant(headers=keep)
    assert keep[celery_ctx.HEADER] == 99
    token = context._current.set(None)                     # a process with no explicit tenant: nothing stamped
    try:
        h2 = {}
        celery_ctx.stamp_tenant(headers=h2)
        assert celery_ctx.HEADER not in h2
    finally:
        context._current.reset(token)


@pytest.mark.django_db(transaction=True)
def test_a_real_worker_runs_the_task_for_the_store_it_was_queued_from(store, settings):
    from celery.contrib.testing.worker import start_worker

    from config.celery import app

    @app.task(name="tenancy_test.whoami")
    def whoami():
        return context._current.get()

    with start_worker(app, pool="solo", perform_ping_check=False, shutdown_timeout=10):
        with _in(store):
            r_store = app.send_task("tenancy_test.whoami")      # through the broker, never eager
        token = context._current.set(None)
        try:
            r_plain = app.send_task("tenancy_test.whoami")
        finally:
            context._current.reset(token)
        assert r_store.get(timeout=20) == store.pk
        assert r_plain.get(timeout=20) is None                  # no header → the worker's default, as before


def test_periodic_retry_queues_each_stores_orders_in_its_own_context(store, panel, monkeypatch):
    from django.utils import timezone

    from apps.orders import tasks

    seen = []
    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda oid: seen.append((oid, context._current.get())))
    old = timezone.now() - timezone.timedelta(minutes=10)
    ours = Order.objects.create(user=User.objects.create_user("ours1", "Str0ngPass!"), plan=_plan(panel),
                                type=OrderType.NEW, status=OrderStatus.PAID, amount=1, amount_unique=1, unique_expire_at=_soon())
    with _in(store):
        theirs = Order.objects.create(user=User.objects.create_user("theirs1", "Str0ngPass!"), plan=_plan(panel),
                                      type=OrderType.NEW, status=OrderStatus.PAID, amount=1, amount_unique=1, unique_expire_at=_soon())
    Order.objects.filter(pk=ours.pk).update(updated_at=old)
    with _in(store):
        Order.objects.filter(pk=theirs.pk).update(updated_at=old)
    assert tasks.retry_unfulfilled_orders() == {"redispatched": 2}
    assert (theirs.pk, store.pk) in seen and any(oid == ours.pk for oid, _ in seen)


# ------------------------------------------------------------------ set_owner
def _token(rsps):
    rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"}, status=200)


def _user_json(name, owner):
    return {"username": name, "status": "on_hold", "data_limit": 10 * GB, "used_traffic": 0, "expire": None,
            "subscription_url": f"/sub/{name}", "note": "", "admin": {"id": 1, "username": owner}}


def test_a_store_service_is_handed_to_the_reseller_and_read_back(store, panel):
    with _in(store):
        u = User.objects.create_user("buyer1", "Str0ngPass!")
        plan = _plan(panel)
        svc = Service.objects.create(user=u, panel=panel, panel_username="buyer_1", current_plan=plan, status=ServiceStatus.PENDING)
        with responses.RequestsMock() as rsps:
            _token(rsps)
            rsps.add(responses.POST, f"{BASE}/api/user", json=_user_json("buyer_1", "adm"), status=200)
            rsps.add(responses.PUT, f"{BASE}/api/user/buyer_1/set_owner?admin_username=seller1",
                     json=_user_json("buyer_1", "seller1"), status=200)
            rsps.add(responses.GET, f"{BASE}/api/user/buyer_1", json=_user_json("buyer_1", "seller1"), status=200)
            from apps.panel.services import provision_service

            provision_service(svc.pk)
        svc.refresh_from_db()
        assert svc.status == ServiceStatus.ON_HOLD


def test_set_owner_that_does_not_take_is_an_error(store, panel):
    with _in(store):
        u = User.objects.create_user("buyer2", "Str0ngPass!")
        svc = Service.objects.create(user=u, panel=panel, panel_username="buyer_2", current_plan=_plan(panel),
                                     status=ServiceStatus.PENDING)
        with responses.RequestsMock() as rsps:
            _token(rsps)
            rsps.add(responses.POST, f"{BASE}/api/user", json=_user_json("buyer_2", "adm"), status=200)
            rsps.add(responses.PUT, f"{BASE}/api/user/buyer_2/set_owner?admin_username=seller1", json={}, status=200)
            rsps.add(responses.GET, f"{BASE}/api/user/buyer_2", json=_user_json("buyer_2", "adm"), status=200)
            from apps.panel.services import provision_service

            with pytest.raises(PanelError, match="set_owner did not take"):
                provision_service(svc.pk)


def test_our_own_services_are_never_handed_over(panel):
    u = User.objects.create_user("ourbuyer", "Str0ngPass!")
    svc = Service.objects.create(user=u, panel=panel, panel_username="our_1", current_plan=_plan(panel), status=ServiceStatus.PENDING)
    with responses.RequestsMock() as rsps:                  # a set_owner call would fail: not registered
        _token(rsps)
        rsps.add(responses.POST, f"{BASE}/api/user", json=_user_json("our_1", "adm"), status=200)
        from apps.panel.services import provision_service

        provision_service(svc.pk)


# ------------------------------------------------------------------ quota guard
def test_quota_counts_open_orders_and_blocks_short_sales(store, panel, alerts):
    with _in(store):
        st = quota.state()
        assert st["limited"] and st["remaining"] == 60 * GB and st["reserved"] == 0 and st["percent_remaining"] == 60.0
        quota.check(50 * GB)
        u = User.objects.create_user("q1", "Str0ngPass!")
        from django.utils import timezone

        Order.objects.create(user=u, plan=_plan(panel, 30), type=OrderType.NEW, status=OrderStatus.PENDING_PAYMENT,
                             amount=1, amount_unique=1, unique_expire_at=timezone.now() + timezone.timedelta(minutes=10))
        Order.objects.create(user=u, plan=_plan(panel, 20), type=OrderType.NEW, status=OrderStatus.PAID, amount=1, amount_unique=1, unique_expire_at=_soon())
        Order.objects.create(user=u, plan=_plan(panel, 99), type=OrderType.NEW, status=OrderStatus.PENDING_PAYMENT,
                             amount=1, amount_unique=1, unique_expire_at=timezone.now() - timezone.timedelta(minutes=1))
        assert quota.state()["reserved"] == 50 * GB                 # the expired reservation does not count
        with pytest.raises(quota.QuotaShort) as exc:
            quota.check(20 * GB)
        assert exc.value.detail["available"] == 10 * GB and "در دسترس نیست" in exc.value.message("fa")
        with pytest.raises(quota.QuotaShort):
            quota.check(20 * GB)
    assert AgencyNotice.objects.filter(admin_username="seller1", kind="quota_short").count() == 1   # once an hour
    assert len([a for a in alerts if "حجم ناکافی" in a]) == 1


def test_unlimited_resellers_are_never_blocked_and_our_store_is_never_checked(store, reseller):
    quota.check(10 ** 18)                                           # default tenant
    PanelAdmin.objects.filter(pk=reseller.pk).update(has_data_limit=False, admin_limit_bytes=0)
    with _in(store):
        quota.check(10 ** 18)
        quota.check(None)


def test_unlimited_plan_and_missing_reseller_are_refused(store, reseller):
    with _in(store):
        with pytest.raises(quota.QuotaShort) as exc:
            quota.check(None)
        assert exc.value.detail["why"] == "unlimited_plan"
        PanelAdmin.objects.filter(pk=reseller.pk).update(username="someone-else")
        with pytest.raises(quota.QuotaShort) as exc:
            quota.check(GB)
        assert exc.value.detail["why"] == "no_reseller"


def test_near_the_limit_the_number_is_recomputed_live(store, monkeypatch):
    monkeypatch.setattr(quota, "_live_remaining", lambda pa: 5 * GB)
    with _in(store):
        quota.check(30 * GB)                                       # synced 60 GB − 30 GB leaves 30 % → no live call
        with pytest.raises(quota.QuotaShort):
            quota.check(55 * GB)                                   # would leave 5 % → live: only 5 GB left


def test_a_store_customer_gets_a_friendly_refusal_and_no_order(store, panel, alerts):
    with _in(store):
        plan = _plan(panel, 80)
        u = User.objects.create_user("q2", "Str0ngPass!")
    c = APIClient(HTTP_HOST=HOST)
    c.force_authenticate(u)
    r = c.post("/api/v1/orders/", {"plan": plan.pk, "type": "new", "requested_account_name": "q2_acc"}, format="json")
    assert r.status_code == 400, r.content
    assert r.json()["code"] == "quota" and "در دسترس نیست" in r.json()["detail"]
    with _in(store):
        assert not Order.objects.exists()


def test_paid_order_waits_for_quota_then_is_delivered(store, panel, monkeypatch, alerts):
    from apps.orders import tasks

    calls = []
    monkeypatch.setattr("apps.panel.services.provision_service", lambda sid, plan=None: calls.append(sid))
    with _in(store):
        u = User.objects.create_user("q3", "Str0ngPass!")
        o = Order.objects.create(user=u, plan=_plan(panel, 70), type=OrderType.NEW, status=OrderStatus.PAID,
                                 amount=1, amount_unique=1, requested_account_name="q3_acc", unique_expire_at=_soon())
        out = tasks.fulfill_order.run(o.pk)
        assert out["waiting"] == "quota" and calls == []
        o.refresh_from_db()
        assert o.status == OrderStatus.PAID and o.provision_failed_at is None   # the retry job keeps trying
    PanelAdmin.objects.filter(username="seller1").update(admin_remaining=90 * GB)
    with _in(store):
        out = tasks.fulfill_order.run(o.pk)
        assert out["status"] == "completed" and len(calls) == 1


def test_warnings_at_20_and_10_percent_once_each(store, reseller, alerts):
    def at(pct):
        PanelAdmin.objects.filter(pk=reseller.pk).update(admin_remaining=pct * GB)
        return quota.warn_all()

    assert at(25)["warned"] == {}
    assert at(18)["warned"] == {"seller1": 20}
    assert at(17)["warned"] == {}
    assert at(8)["warned"] == {"seller1": 10}
    assert at(8)["warned"] == {}
    assert AgencyNotice.objects.filter(admin_username="seller1", kind="quota_low").count() == 2
    at(50)
    store.refresh_from_db()
    assert store.quota_alert_level == 0
    assert at(15)["warned"] == {"seller1": 20}                      # after a raise, warned again


def test_store_dashboard_shows_the_quota(store, reseller):
    PanelAdmin.objects.filter(pk=reseller.pk).update(admin_remaining=15 * GB)
    boss = staff_client("super", "q-dash")
    boss.defaults["HTTP_HOST"] = HOST
    q = boss.get("/api/v1/admin/dashboard/").json()["quota"]
    assert q["limited"] and q["level"] == 20 and q["percent_remaining"] == 15.0
    assert "reserved" not in q and "remaining" not in q


# ------------------------------------------------------------------ store plans
@pytest.fixture
def catalog_env(monkeypatch, panel):
    from apps.agency import panel_api
    from apps.tenancy import catalog

    monkeypatch.setattr(panel_api, "agency_panel", lambda: panel)
    monkeypatch.setattr(catalog, "allowed_groups", lambda t: {"all": False, "groups": [{"id": 3, "name": "DE"}]})
    return panel


def test_store_plans_are_bounded_by_the_resellers_admin(store, catalog_env, reseller):
    other = Panel.objects.create(name="Other", base_url="https://o.test", admin_username="a", admin_password_enc="p")
    boss = staff_client("super", "plans-boss")
    boss.defaults["HTTP_HOST"] = HOST
    opts = boss.get("/api/v1/admin/plans/store-options/").json()
    assert opts["panel"]["id"] == catalog_env.pk and opts["groups"] == [{"id": 3, "name": "DE"}] and opts["unlimited_ok"] is False
    base = {"name_fa": "پلن فروشگاه", "price": 90000, "duration_days": 30, "data_limit": 10 * GB, "type": "fixed"}
    r = boss.post("/api/v1/admin/plans/", {**base, "panel": other.pk}, format="json")
    assert r.status_code == 400 and "panel" in r.json()
    r = boss.post("/api/v1/admin/plans/", {**base, "group_ids": [7]}, format="json")
    assert r.status_code == 400 and "group_ids" in r.json()
    r = boss.post("/api/v1/admin/plans/", {**base, "data_limit": None}, format="json")
    assert r.status_code == 400 and "data_limit" in r.json()
    r = boss.post("/api/v1/admin/plans/", {**base, "group_ids": [3]}, format="json")
    assert r.status_code == 201, r.content
    p = Plan.objects.none()
    with _in(store):
        p = Plan.objects.get(name_fa="پلن فروشگاه")
        assert p.panel_id == catalog_env.pk and p.tenant_id == store.pk
    assert not Plan.objects.filter(name_fa="پلن فروشگاه").exists()          # never in our store
    assert [x["name_fa"] for x in boss.get("/api/v1/admin/plans/").json()["results"]] == ["پلن فروشگاه"]
    assert staff_client("super", "ours-p").get("/api/v1/admin/plans/store-options/").status_code == 404


def test_our_plans_are_unchanged(catalog_env):
    boss = staff_client("super", "our-plans")
    r = boss.post("/api/v1/admin/plans/", {"name_fa": "ما", "price": 1, "duration_days": 30, "data_limit": None,
                                           "type": "fixed", "panel": catalog_env.pk}, format="json")
    assert r.status_code == 201, r.content
