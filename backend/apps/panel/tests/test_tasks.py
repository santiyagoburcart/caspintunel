from decimal import Decimal

import pytest
import responses

from apps.accounts.models import User
from apps.panel.models import Panel, Service, ServiceStatus
from apps.panel.tasks import sync_all_services
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db
BASE = "https://panel.test"


@responses.activate
def test_sync_all_services_dispatches_for_live_services(settings):
    settings.PANEL_SYNC_ENABLED = True
    panel = Panel.objects.create(name="T", base_url=BASE, admin_username="a", admin_password_enc="p")
    user = User.objects.create_user("c", "Str0ngPass!")
    plan = Plan.objects.create(name_fa="p", price=Decimal("1"))
    Service.objects.create(user=user, panel=panel, panel_username="a-1", current_plan=plan,
                           status=ServiceStatus.ACTIVE)
    Service.objects.create(user=user, panel=panel, panel_username="a-2", current_plan=plan,
                           status=ServiceStatus.EXPIRED)  # not synced

    responses.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add(responses.GET, f"{BASE}/api/user/a-1",
                  json={"username": "a-1", "used_traffic": 5, "status": "active"}, status=200)

    result = sync_all_services()
    assert result["dispatched"] == 1


def test_sync_all_services_skips_without_panel(settings):
    settings.PANEL_SYNC_ENABLED = True
    assert "skipped" in sync_all_services()
