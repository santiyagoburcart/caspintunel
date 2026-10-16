"""Data for the redesigned agency pages: sort keys, set-limit preview (= what
set_limit then does), portal link + QR following the configured path."""
import io
from decimal import Decimal

import pytest
import responses
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import Staff
from apps.adminpanel.tokens import issue_tokens
from apps.agency import ledger
from apps.agency.enrich import _enrich, hidden_value
from apps.agency.models import LedgerEntry, PanelAdmin
from apps.agency.models import _fmt_bytes
from apps.panel.models import Panel
from apps.settings_app.models import SiteConfig, ValueType
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db
GB = 1024 ** 3
BASE = "https://sigma.test"


@pytest.fixture
def c():
    Panel.objects.create(name="sigma", base_url=BASE, admin_username="u", admin_password_enc="p", is_active=True)
    PanelAdmin.objects.create(username="ali", has_data_limit=True, admin_limit_bytes=500 * GB, admin_remaining=100 * GB,
                              total_user_limit=650 * GB, total_user_used=400 * GB, user_count=12, active_user_count=9)
    PanelAdmin.objects.create(username="bea", total_user_limit=5 * GB, total_user_used=7 * GB, user_count=3, active_user_count=3)
    s = Staff(username="boss", is_superadmin=True); s.set_password("x-Str0ng!"); s.save()
    cl = APIClient(); cl.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return cl


def test_rows_carry_raw_sort_keys_selected_from_the_model(c):
    rows = {r["username"]: r for r in c.get("/api/v1/admin/agency/admins/").json()["results"]}
    a = PanelAdmin.objects.get(username="ali")
    s = rows["ali"]["sort"]
    assert s == {"total_sold": a.total_user_limit, "used": a.total_user_used, "remaining": a.admin_remaining,
                 "hidden": hidden_value(a), "sold_limit": _enrich(a)["sold_limit_value"], "usage": a.usage_percent,
                 "users": 12, "active": 9, "limit": a.admin_limit_bytes}
    assert _fmt_bytes(hidden_value(a)) == _enrich(a)["hidden_traffic_fmt"]      # same expression as PAMP's view


@responses.activate
def test_preview_equals_what_set_limit_then_does(c):
    set_setting("agency_sync_enabled", True, ValueType.BOOL)
    ledger.set_price("ali", 1200, ledger.today())
    p = c.post("/api/v1/admin/agency/admins/ali/set-limit/preview/", {"action": "add", "value_gb": 300}, format="json").json()
    assert p["old_limit_fmt"] == "500.00 GB" and p["new_limit_fmt"] == "800.00 GB"
    assert Decimal(str(p["charge"]["gb"])) == Decimal("300") and p["charge"]["price_per_gb"] == 1200 and p["charge"]["amount"] == 360000
    assert not LedgerEntry.objects.exists() and PanelAdmin.objects.get(username="ali").admin_limit_bytes == 500 * GB
    responses.add("POST", f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add("PUT", f"{BASE}/api/admin/ali", json={})
    assert c.post("/api/v1/admin/agency/admins/ali/set-limit/", {"action": "add", "value_gb": 300}, format="json").status_code == 200
    a = PanelAdmin.objects.get(username="ali")
    assert a.admin_limit_bytes == p["new_limit_bytes"] and LedgerEntry.objects.get().amount == p["charge"]["amount"]


def test_preview_validation_and_no_charge_on_reduce(c):
    assert c.post("/api/v1/admin/agency/admins/ali/set-limit/preview/", {"action": "add", "value_gb": "x"}, format="json").status_code == 400
    assert c.post("/api/v1/admin/agency/admins/ali/set-limit/preview/", {"action": "add", "value_gb": -5}, format="json").status_code == 400
    assert c.post("/api/v1/admin/agency/admins/ali/set-limit/preview/", {"action": "nope", "value_gb": 1}, format="json").status_code == 400
    p = c.post("/api/v1/admin/agency/admins/ali/set-limit/preview/", {"action": "reduce", "value_gb": 100}, format="json").json()
    assert p["new_limit_fmt"] == "400.00 GB" and p["charge"] is None


def test_portal_link_follows_the_configured_path(c, tmp_path, settings):
    settings.UPDATE_SENTINEL_PATH = str(tmp_path / ".update-requested")
    cfg = SiteConfig.load(); cfg.site_domain = "aicaspin.ir"; cfg.save()
    assert c.get("/api/v1/admin/agency/portal-link/").json() == {"path": "/agency", "url": "https://aicaspin.ir/agency/"}
    (tmp_path / ".paths-status.json").write_text('{"ok": true, "admin": "/panel", "portal": "/resellers"}')
    assert c.get("/api/v1/admin/agency/portal-link/").json()["url"] == "https://aicaspin.ir/resellers/"
    r = c.get("/api/v1/admin/agency/portal-link/qr.png")
    assert r.status_code == 200 and r["Content-Type"] == "image/png" and Image.open(io.BytesIO(r.content)).size[0] > 100
