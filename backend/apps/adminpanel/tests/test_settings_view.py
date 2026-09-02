"""/admin/settings/ — runtime key-value settings editable from the panel."""
import pytest

from apps.adminpanel.tests.conftest import make_staff
from apps.settings_app.utils import get_setting

pytestmark = pytest.mark.django_db


@pytest.fixture
def boss(staff_client, superadmin):
    return staff_client(superadmin)


def test_get_returns_editable_settings(boss):
    r = boss.get("/api/v1/admin/settings/")
    assert r.status_code == 200
    keys = {s["key"] for s in r.data["settings"]}
    assert "backup_interval_minutes" in keys
    assert "unique_amount_reservation_minutes" in keys


def test_put_updates_backup_interval(boss):
    r = boss.put("/api/v1/admin/settings/", {"backup_interval_minutes": 360}, format="json")
    assert r.status_code == 200
    assert get_setting("backup_interval_minutes") == 360
    row = next(s for s in r.data["settings"] if s["key"] == "backup_interval_minutes")
    assert row["value"] == 360


def test_put_clamps_out_of_range_int(boss):
    boss.put("/api/v1/admin/settings/", {"backup_interval_minutes": 1}, format="json")
    assert get_setting("backup_interval_minutes") == 5   # clamped to the minimum


def test_put_coerces_bool(boss):
    boss.put("/api/v1/admin/settings/", {"email_verification_required": True}, format="json")
    assert get_setting("email_verification_required") is True


def test_put_ignores_unknown_keys(boss):
    r = boss.put("/api/v1/admin/settings/", {"SECRET_KEY": "hacked", "backup_interval_minutes": 120}, format="json")
    assert r.status_code == 200
    assert get_setting("backup_interval_minutes") == 120


def test_settings_needs_settings_manage(staff_client, perms):
    weak = staff_client(make_staff("weak", ["monitoring.view"], perms))
    assert weak.get("/api/v1/admin/settings/").status_code == 403


def test_product_display_mode_default_and_enum(boss):
    row = next(s for s in boss.get("/api/v1/admin/settings/").data["settings"]
               if s["key"] == "product_display_mode")
    assert row["value"] == "grouped"                       # default

    assert boss.put("/api/v1/admin/settings/", {"product_display_mode": "flat"},
                    format="json").status_code == 200
    assert get_setting("product_display_mode") == "flat"

    bad = boss.put("/api/v1/admin/settings/", {"product_display_mode": "sideways"},
                   format="json")
    assert bad.status_code == 400
    assert get_setting("product_display_mode") == "flat"   # unchanged


def test_public_config_exposes_display_mode(api):
    from apps.settings_app.utils import set_setting

    assert api.get("/api/v1/config/").data["product_display_mode"] == "grouped"
    set_setting("product_display_mode", "flat", "str")
    assert api.get("/api/v1/config/").data["product_display_mode"] == "flat"
