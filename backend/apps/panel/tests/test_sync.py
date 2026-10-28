"""Service sync (v1.28): every linked service is pulled from PasarGuard whatever its
status, a renewal / usage reset made directly on PasarGuard shows up here, the sync
buttons report real numbers, and reminders never go out from stale data."""
from datetime import timedelta
from decimal import Decimal

import pytest
import responses
from django.utils import timezone
from rest_framework.test import APIClient

from apps.common.models import AuditLog
from apps.crm import retention as R
from apps.crm.tests.test_crm import client_for
from apps.crm.tests.test_crm import staff as make_staff
from apps.crm.models import ServiceWarning, WarningKind, WarningRule
from apps.panel.models import Panel, Service, ServiceStatus
from apps.panel.services import refresh_watchable_services, sync_service_detail
from apps.panel.tasks import sync_all_services
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db
BASE = "https://panel.test"
GB = 1024 ** 3
MB = 1024 ** 2


@pytest.fixture
def panel():
    return Panel.objects.create(name="T", base_url=BASE, admin_username="a", admin_password_enc="p", is_active=True)


@pytest.fixture
def svc(panel):
    from apps.accounts.models import User

    u = User.objects.create_user("tg_63e47a2c", "Str0ngPass!")
    plan = Plan.objects.create(name_fa="p", price=Decimal("1"), panel=panel, data_limit=50 * GB, duration_days=30)
    past = timezone.now() - timedelta(hours=1)
    return Service.objects.create(user=u, panel=panel, panel_username="hadis_sadeghi", current_plan=plan, source="import",
                                  status=ServiceStatus.EXPIRED, expire_at=past, data_limit=50 * GB,
                                  data_used=int(43.7 * GB), alert_vol_sent=True, alert_exp_sent=True,
                                  last_synced_at=past)


def renewed_on_panel(rsps, name="hadis_sadeghi", **over):
    rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    body = {"username": name, "status": "active", "expire": (timezone.now() + timedelta(days=31)).isoformat(),
            "data_limit": 50 * GB, "used_traffic": int(9.71 * MB), "online_at": timezone.now().isoformat(),
            "subscription_url": "/sub/abc", **over}
    rsps.add(responses.GET, f"{BASE}/api/user/{name}", json=body)


@responses.activate
def test_renewal_done_on_pasarguard_is_pulled_for_an_expired_service(settings, svc):
    """The hadis_sadeghi case: linked, then renewed directly on PasarGuard (usage reset)."""
    settings.PANEL_SYNC_ENABLED = True
    renewed_on_panel(responses)
    res = sync_all_services()
    assert res["checked"] == 1 and res["updated"] == 1 and res["errors"] == 0
    svc.refresh_from_db()
    assert svc.status == ServiceStatus.ACTIVE
    assert svc.expire_at > timezone.now() + timedelta(days=30)
    assert svc.data_used == int(9.71 * MB)
    assert svc.online_at is not None
    assert not svc.alert_vol_sent and not svc.alert_exp_sent           # reminders re-armed for the new period
    log = AuditLog.objects.get(action="service.changed_on_panel")
    assert set(log.detail["kinds"]) >= {"expiry_extended", "usage_reset", "reactivated"}
    row = res["rows"][0]
    assert row["panel_username"] == "hadis_sadeghi" and "status" in row["changed"] and "expire_at" in row["changed"]


@responses.activate
def test_nothing_changed_is_not_an_update(svc):
    """PasarGuard signs the subscription link per read and online_at moves: not an update."""
    renewed_on_panel(responses)
    sync_service_detail(svc.id)
    responses.reset()
    renewed_on_panel(responses, subscription_url="/sub/other-signature",
                     used_traffic=int(9.71 * MB), online_at=(timezone.now() + timedelta(seconds=30)).isoformat())
    svc.refresh_from_db()
    renewed_expire = svc.expire_at.isoformat()
    responses.reset()
    renewed_on_panel(responses, subscription_url="/sub/other-signature", expire=renewed_expire,
                     online_at=(timezone.now() + timedelta(seconds=30)).isoformat())
    out = sync_service_detail(svc.id)
    assert out.changed == [] and not out.updated


@responses.activate
def test_missing_on_panel_counts_as_error(settings, svc):
    settings.PANEL_SYNC_ENABLED = True
    responses.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add(responses.GET, f"{BASE}/api/user/hadis_sadeghi", json={"detail": "User not found"}, status=404)
    res = sync_all_services()
    assert res["errors"] == 1 and res["rows"][0]["error"] == "not_found"


@pytest.fixture
def staff():
    return make_staff("op", perms=("services.manage", "monitoring.view"))


def _client(st):
    return client_for(st)


@responses.activate
def test_sync_button_runs_the_sync_and_reports_numbers(svc, staff):
    renewed_on_panel(responses)
    r = _client(staff).post("/api/v1/admin/services/sync-now/")
    assert r.status_code == 200, r.content
    d = r.json()
    assert (d["checked"], d["updated"], d["errors"], d["skipped"]) == (1, 1, 0, 0)
    assert d["rows"][0]["status"] == "active"
    assert AuditLog.objects.filter(action="service.sync_all", staff_id=staff.id).exists()


@responses.activate
def test_per_row_sync(svc, staff):
    renewed_on_panel(responses)
    r = _client(staff).post(f"/api/v1/admin/services/{svc.id}/sync/")
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["updated"] == 1 and d["service"]["status"] == "active"


def test_sync_needs_services_manage(svc):
    st = make_staff("v", perms=("monitoring.view",))
    assert _client(st).post("/api/v1/admin/services/sync-now/").status_code == 403
    assert _client(st).post(f"/api/v1/admin/services/{svc.id}/sync/").status_code == 403


@responses.activate
def test_customer_view_refreshes_an_expired_service(svc):
    renewed_on_panel(responses)
    assert refresh_watchable_services([svc]) == 1
    svc.refresh_from_db()
    assert svc.status == "active"


# ------------------------------------------------------------------ reminders vs stale data
@pytest.fixture
def rule95():
    WarningRule.objects.all().delete()
    return WarningRule.objects.create(kind=WarningKind.DATA, threshold=95, title_fa="t", body_fa="b", is_active=True)


@responses.activate
def test_no_volume_warning_when_the_service_was_reset_on_the_panel(svc, rule95, monkeypatch):
    """Our row still says 49 / 50 GB used, but PasarGuard reset the usage: no warning."""
    monkeypatch.setattr(R, "deliver_pending", lambda now=None: {})
    Service.objects.filter(pk=svc.pk).update(status="active", data_used=49 * GB, alert_vol_sent=False,
                                             expire_at=timezone.now() + timedelta(days=10),
                                             last_synced_at=timezone.now() - timedelta(minutes=10))
    renewed_on_panel(responses)
    R.run_warnings()
    assert not ServiceWarning.objects.exists()
    svc.refresh_from_db()
    assert svc.data_used == int(9.71 * MB)


@responses.activate
def test_no_warning_when_the_panel_cannot_be_asked(svc, rule95, monkeypatch):
    monkeypatch.setattr(R, "deliver_pending", lambda now=None: {})
    Service.objects.filter(pk=svc.pk).update(status="active", data_used=49 * GB,
                                             expire_at=timezone.now() + timedelta(days=10),
                                             last_synced_at=timezone.now() - timedelta(minutes=10))
    responses.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add(responses.GET, f"{BASE}/api/user/hadis_sadeghi", json={"detail": "down"}, status=502)
    R.run_warnings()
    assert not ServiceWarning.objects.exists()


@responses.activate
def test_warning_still_goes_out_when_the_panel_agrees(svc, rule95, monkeypatch):
    monkeypatch.setattr(R, "deliver_pending", lambda now=None: {})
    Service.objects.filter(pk=svc.pk).update(status="active", data_used=49 * GB,
                                             expire_at=timezone.now() + timedelta(days=10),
                                             last_synced_at=timezone.now() - timedelta(minutes=10))
    renewed_on_panel(responses, used_traffic=49 * GB, expire=(timezone.now() + timedelta(days=10)).isoformat())
    R.run_warnings()
    assert ServiceWarning.objects.filter(threshold=95).count() == 1


def test_queued_warning_dropped_after_a_renewal(svc, rule95):
    """Made during quiet hours, then the service was renewed: bot / email never go out."""
    Service.objects.filter(pk=svc.pk).update(status="active", data_used=49 * GB,
                                             expire_at=timezone.now() + timedelta(days=10))
    svc.refresh_from_db()
    w = ServiceWarning.objects.create(service=svc, rule=rule95, kind="data", threshold=95, period_key=R.period_key(svc),
                                      due_at=timezone.now())
    Service.objects.filter(pk=svc.pk).update(data_used=10 * MB, expire_at=timezone.now() + timedelta(days=40))
    R.deliver_pending()
    w.refresh_from_db()
    assert w.bot_sent_at and w.bot_error.startswith("skipped") and w.notification_id is None
