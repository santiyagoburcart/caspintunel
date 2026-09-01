from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.ops.alerts import run_service_alerts
from apps.panel.models import Panel, Service, ServiceStatus
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db

_GB = 1024**3


@pytest.fixture
def svc():
    user = User.objects.create_user("u", "Str0ngPass!")
    panel = Panel.objects.create(name="P", base_url="https://x", admin_username="a", admin_password_enc="p")
    return Service.objects.create(user=user, panel=panel, panel_username="s1",
                                  status=ServiceStatus.ACTIVE, data_limit=10 * _GB, data_used=0)


@pytest.fixture(autouse=True)
def _capture_notify(monkeypatch):
    sent = []
    monkeypatch.setattr("apps.ops.alerts.notify_user",
                        lambda user, **kw: sent.append(kw) or None)
    return sent


def test_volume_alert_fires_once(svc, _capture_notify):
    set_setting("alert_volume_percent", "80", "int")
    svc.data_used = int(8.5 * _GB)
    svc.save()

    assert run_service_alerts()["volume_alerts"] == 1
    svc.refresh_from_db()
    assert svc.alert_vol_sent is True
    assert "حجم" in _capture_notify[0]["title"]

    # second run: flag already set -> no repeat
    assert run_service_alerts()["volume_alerts"] == 0


def test_no_volume_alert_below_threshold(svc, _capture_notify):
    set_setting("alert_volume_percent", "80", "int")
    svc.data_used = int(5 * _GB)
    svc.save()
    assert run_service_alerts()["volume_alerts"] == 0


def test_expiry_alert_fires_within_window(svc, _capture_notify):
    set_setting("alert_expire_days", "3", "int")
    svc.expire_at = timezone.now() + timedelta(days=2)
    svc.save()

    assert run_service_alerts()["expiry_alerts"] == 1
    svc.refresh_from_db()
    assert svc.alert_exp_sent is True

    assert run_service_alerts()["expiry_alerts"] == 0


def test_expiry_alert_not_fired_when_far_out(svc, _capture_notify):
    set_setting("alert_expire_days", "3", "int")
    svc.expire_at = timezone.now() + timedelta(days=20)
    svc.save()
    assert run_service_alerts()["expiry_alerts"] == 0
