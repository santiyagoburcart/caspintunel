from datetime import timedelta
from decimal import Decimal

import pytest
import responses
from django.utils import timezone

from apps.accounts.models import User
from apps.panel.mappers import build_create_payload, build_renew_payload
from apps.panel.models import ExpireStrategy, Panel, Service, ServiceStatus
from apps.panel.services import provision_service, renew_service, sync_service
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db
BASE = "https://panel.test"


@pytest.fixture
def panel():
    return Panel.objects.create(
        name="T", base_url=BASE, admin_username="adm", admin_password_enc="pw",
        default_group_ids=[1, 2],
    )


@pytest.fixture
def user():
    return User.objects.create_user("cust", "Str0ngPass!")


@pytest.fixture
def timed_plan(panel):
    return Plan.objects.create(panel=panel, name_fa="30d", price=Decimal("100000"),
                               data_limit=50 * 1024**3, duration_days=30, group_ids=[1, 2])


def _svc(user, panel, plan, **over):
    defaults = dict(user=user, panel=panel, panel_username="cust-1", current_plan=plan,
                    status=ServiceStatus.PENDING)
    defaults.update(over)
    return Service.objects.create(**defaults)


def _token(rsps):
    rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"}, status=200)


# --- payload mapping ---------------------------------------------
def test_timed_plan_maps_to_on_hold(user, panel, timed_plan):
    payload = build_create_payload(_svc(user, panel, timed_plan), timed_plan, panel)
    assert payload["status"] == "on_hold"
    assert payload["on_hold_expire_duration"] == 30 * 86400
    assert payload["data_limit"] == 50 * 1024**3
    assert payload["group_ids"] == [1, 2]          # from the plan


def test_group_ids_fall_back_to_panel_default(user, panel):
    panel.default_group_ids = [9]
    panel.save()
    plan = Plan.objects.create(panel=panel, name_fa="p", price=Decimal("1"), duration_days=7, group_ids=[])
    payload = build_create_payload(_svc(user, panel, plan), plan, panel)
    assert payload["group_ids"] == [9]


def test_new_plan_inherits_panel_default_groups_by_default(user, panel):
    """A plan created without an explicit group_ids must NOT bake in every panel
    group — it inherits Panel.default_group_ids, so unchecking a group there
    actually takes effect."""
    panel.default_group_ids = [5, 6, 8]
    panel.save()
    plan = Plan.objects.create(panel=panel, name_fa="p", price=Decimal("1"), duration_days=7)
    assert plan.group_ids == []
    payload = build_create_payload(_svc(user, panel, plan), plan, panel)
    assert payload["group_ids"] == [5, 6, 8]   # exactly the panel default, no wirgard


@responses.activate
def test_created_panel_user_gets_plan_group_ids(user, panel):
    import json
    _token(responses)
    plan = Plan.objects.create(panel=panel, name_fa="p", price=Decimal("1"), duration_days=7, group_ids=[6, 8])
    responses.add(responses.POST, f"{BASE}/api/user",
                  json={"username": "cust-1", "status": "on_hold", "subscription_url": "/myac/z/"},
                  status=200)
    provision_service(_svc(user, panel, plan).id)
    create_call = next(c for c in responses.calls if c.request.url.endswith("/api/user")
                       and c.request.method == "POST")
    assert json.loads(create_call.request.body)["group_ids"] == [6, 8]


def test_timeless_plan_maps_to_active_no_expire(user, panel):
    plan = Plan.objects.create(panel=panel, name_fa="inf", price=Decimal("1"), data_limit=0, duration_days=None)
    payload = build_create_payload(_svc(user, panel, plan), plan, panel)
    assert payload["status"] == "active"
    assert payload["expire"] is None


def test_renew_payload_extends_from_current_expiry(user, panel, timed_plan):
    future = timezone.now() + timedelta(days=5)
    svc = _svc(user, panel, timed_plan, expire_at=future, status=ServiceStatus.ACTIVE)
    payload = build_renew_payload(svc, timed_plan)
    assert payload["status"] == "active"
    assert payload["expire"] > (future + timedelta(days=29)).isoformat()


# --- provisioning ---------------------------------------------
@responses.activate
def test_provision_creates_and_stores_subscription(user, panel, timed_plan):
    _token(responses)
    responses.add(
        responses.POST, f"{BASE}/api/user",
        json={"username": "cust-1", "subscription_url": "/myac/abc/", "data_limit": 50 * 1024**3,
              "status": "on_hold", "on_hold_expire_duration": 2592000},
        status=200,
    )
    out = provision_service(_svc(user, panel, timed_plan).id)
    assert out.subscription_url == f"{BASE}/myac/abc/"
    assert out.status == ServiceStatus.ON_HOLD
    assert out.expire_strategy == ExpireStrategy.ON_HOLD


@responses.activate
def test_provision_is_idempotent_on_conflict(user, panel, timed_plan):
    _token(responses)
    responses.add(responses.POST, f"{BASE}/api/user", status=409)
    responses.add(responses.GET, f"{BASE}/api/user/cust-1",
                  json={"username": "cust-1", "subscription_url": f"{BASE}/myac/xyz/", "status": "on_hold"},
                  status=200)
    out = provision_service(_svc(user, panel, timed_plan).id)
    assert out.subscription_url == f"{BASE}/myac/xyz/"


@responses.activate
def test_renew_resets_usage_and_keeps_url(user, panel, timed_plan):
    _token(responses)
    svc = _svc(user, panel, timed_plan, status=ServiceStatus.EXPIRED,
               subscription_url=f"{BASE}/myac/keep/", data_used=999, alert_exp_sent=True)
    responses.add(responses.PUT, f"{BASE}/api/user/cust-1", json={"username": "cust-1"}, status=200)
    responses.add(responses.POST, f"{BASE}/api/user/cust-1/reset", json={}, status=200)
    responses.add(responses.GET, f"{BASE}/api/user/cust-1",
                  json={"username": "cust-1", "subscription_url": f"{BASE}/myac/keep/",
                        "used_traffic": 0, "status": "active", "expire": "2026-11-01T00:00:00Z"},
                  status=200)
    out = renew_service(svc.id, timed_plan)
    assert out.status == ServiceStatus.ACTIVE
    assert out.subscription_url == f"{BASE}/myac/keep/"
    assert out.data_used == 0
    assert out.alert_exp_sent is False


@responses.activate
def test_sync_marks_missing_user_disabled(user, panel, timed_plan):
    _token(responses)
    svc = _svc(user, panel, timed_plan, status=ServiceStatus.ACTIVE, panel_username="gone-1")
    responses.add(responses.GET, f"{BASE}/api/user/gone-1", status=404)
    assert sync_service(svc.id).status == ServiceStatus.DISABLED


@responses.activate
def test_sync_updates_usage_and_online(user, panel, timed_plan):
    _token(responses)
    svc = _svc(user, panel, timed_plan, status=ServiceStatus.ACTIVE)
    responses.add(responses.GET, f"{BASE}/api/user/cust-1", json={
        "username": "cust-1", "used_traffic": 12345, "data_limit": 50 * 1024**3,
        "online_at": "2026-09-01T10:00:00Z", "status": "active",
        "expire": "2026-10-01T00:00:00Z",
    }, status=200)
    out = sync_service(svc.id)
    assert out.data_used == 12345
    assert out.online_at is not None
    assert out.last_synced_at is not None
    assert out.status == ServiceStatus.ACTIVE
    assert out.expire_strategy == ExpireStrategy.FIXED_DATE


@responses.activate
def test_sync_accepts_unix_timestamp_expire(user, panel, timed_plan):
    _token(responses)
    svc = _svc(user, panel, timed_plan, status=ServiceStatus.ACTIVE)
    responses.add(responses.GET, f"{BASE}/api/user/cust-1",
                  json={"username": "cust-1", "status": "active", "expire": 1790000000}, status=200)
    out = sync_service(svc.id)
    assert out.expire_at is not None and out.expire_at.year == 2026


def test_custom_volume_service_provisions_with_the_right_data_limit():
    """A custom-volume purchase must send the bought GB as data_limit, not 0."""
    from decimal import Decimal

    from apps.accounts.models import User
    from apps.orders.models import OrderType
    from apps.orders.services import create_order
    from apps.orders.tasks import _ensure_service
    from apps.panel.mappers import build_create_payload
    from apps.panel.models import Panel
    from apps.plans.models import Plan, PlanType

    u = User.objects.create_user("cv", "x")
    panel = Panel.objects.create(name="P", base_url="https://x", admin_username="a",
                                 admin_password_enc="p", is_active=True)
    plan = Plan.objects.create(panel=panel, name_fa="CV", type=PlanType.CUSTOM_VOLUME, price=Decimal("0"),
                               price_per_gb=Decimal("2000"), min_gb=1, max_gb=100, group_ids=[6])
    order = create_order(user=u, plan_id=plan.id, order_type=OrderType.NEW, custom_volume_gb=25, requested_account_name="cvprov")

    svc = _ensure_service(order, panel)
    assert svc.data_limit == 25 * 1024**3

    payload = build_create_payload(svc, plan, panel)
    assert payload["data_limit"] == 25 * 1024**3


@responses.activate
def test_fulfill_provisions_on_the_plans_panel_not_the_active_one(user):
    """Multi-panel: the service is created on order.plan.panel even when a
    different panel is the 'active' one."""
    import json

    from apps.orders.models import OrderType
    from apps.orders.services import create_order
    from apps.orders.tasks import fulfill_order

    active = Panel.objects.create(name="Active", base_url="https://active.test",
                                  admin_username="a", admin_password_enc="p", is_active=True,
                                  default_group_ids=[1])
    wg = Panel.objects.create(name="Wireguard", base_url="https://wg.test",
                              admin_username="a", admin_password_enc="p", is_active=True,
                              default_group_ids=[7])
    plan = Plan.objects.create(panel=wg, name_fa="wg", price=Decimal("1"), duration_days=30)
    order = create_order(user=user, plan_id=plan.id, order_type=OrderType.NEW,
                         requested_account_name="wguser")

    responses.add(responses.POST, "https://wg.test/api/admin/token",
                  json={"access_token": "t"}, status=200)
    responses.add(responses.POST, "https://wg.test/api/user",
                  json={"username": "wguser", "status": "on_hold", "subscription_url": "/s/z/"},
                  status=200)

    fulfill_order(order.id)

    order.refresh_from_db()
    assert order.service.panel_id == wg.id
    create_call = next(c for c in responses.calls if c.request.url == "https://wg.test/api/user"
                       and c.request.method == "POST")
    assert json.loads(create_call.request.body)["group_ids"] == [7]   # wg panel default
    # nothing was sent to the "active" panel
    assert not any("active.test" in c.request.url for c in responses.calls)


def test_renew_rejects_a_plan_from_a_different_panel(user, panel):
    other = Panel.objects.create(name="Other", base_url="https://o.test",
                                 admin_username="a", admin_password_enc="p")
    p_other = Plan.objects.create(panel=other, name_fa="o", price=Decimal("1"), duration_days=30)
    svc = _svc(user, panel, Plan.objects.create(panel=panel, name_fa="p", price=Decimal("1")))
    from apps.panel.exceptions import PanelError
    with pytest.raises(PanelError):
        renew_service(svc.id, p_other)
