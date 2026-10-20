"""Change-limit preview on the admin page: the numbers shown before confirming are
exactly what set_limit then does (limit, remaining, ledger charge)."""
from decimal import Decimal

import pytest
import responses
from rest_framework.test import APIClient

from apps.accounts.models import Staff
from apps.adminpanel.tokens import issue_tokens
from apps.agency import ledger
from apps.agency.models import LedgerEntry, PanelAdmin
from apps.panel.models import Panel
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db
GB = 1024 ** 3
BASE = "https://sigma.test"
URL = "/api/v1/admin/agency/admins/ali/set-limit/"


@pytest.fixture
def c():
    Panel.objects.create(name="sigma", base_url=BASE, admin_username="u", admin_password_enc="p", is_active=True)
    PanelAdmin.objects.create(username="ali", has_data_limit=True, admin_limit_bytes=500 * GB, admin_remaining=100 * GB,
                              total_user_limit=650 * GB, total_user_used=400 * GB, user_count=12, active_user_count=9)
    s = Staff(username="boss", is_superadmin=True); s.set_password("x-Str0ng!"); s.save()
    cl = APIClient(); cl.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return cl


@responses.activate
def test_preview_equals_what_set_limit_then_does(c):
    set_setting("agency_sync_enabled", True, ValueType.BOOL)
    ledger.set_price("ali", 1200, ledger.today())
    p = c.post(URL + "preview/", {"action": "add", "value_gb": 300}, format="json").json()
    assert p["old_limit_fmt"] == "500.00 GB" and p["new_limit_fmt"] == "800.00 GB"
    assert Decimal(str(p["charge"]["gb"])) == Decimal("300") and p["charge"]["price_per_gb"] == 1200 and p["charge"]["amount"] == 360000
    assert not LedgerEntry.objects.exists() and PanelAdmin.objects.get(username="ali").admin_limit_bytes == 500 * GB
    responses.add("POST", f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add("PUT", f"{BASE}/api/admin/ali", json={})
    assert c.post(URL, {"action": "add", "value_gb": 300}, format="json").status_code == 200
    a = PanelAdmin.objects.get(username="ali")
    assert a.admin_limit_bytes == p["new_limit_bytes"] and LedgerEntry.objects.get().amount == p["charge"]["amount"]


def test_tb_values_and_validation(c):
    p = c.post(URL + "preview/", {"action": "set", "value_gb": 2 * 1024}, format="json").json()      # 2 TB from the UI
    assert p["new_limit_fmt"] == "2.00 TB"
    for bad in ("x", -5):
        assert c.post(URL + "preview/", {"action": "add", "value_gb": bad}, format="json").status_code == 400
    assert c.post(URL + "preview/", {"action": "nope", "value_gb": 1}, format="json").status_code == 400
    p = c.post(URL + "preview/", {"action": "reduce", "value_gb": 100}, format="json").json()
    assert p["new_limit_fmt"] == "400.00 GB" and p["charge"] is None


def test_branding_logo_and_favicon_uploads_give_a_reason(c):
    from django.core.files.uploadedfile import SimpleUploadedFile

    r = c.patch("/api/v1/admin/branding/", {"logo": SimpleUploadedFile("x.pdf", b"%PDF", content_type="application/pdf")}, format="multipart")
    assert r.status_code == 400 and "PNG" in r.json()["logo"][0]
    big = SimpleUploadedFile("f.png", b"\x89PNG" + b"0" * (600 * 1024), content_type="image/png")
    r = c.patch("/api/v1/admin/branding/", {"favicon": big}, format="multipart")
    assert r.status_code == 400 and "512" in r.json()["favicon"][0]
    r = c.patch("/api/v1/admin/branding/", {"support_telegram": "@help"}, format="multipart")
    assert r.status_code == 200


def test_volume_bytes_match_the_formatted_values(c):
    from apps.agency.enrich import _enrich
    from apps.agency.models import _fmt_bytes

    a = PanelAdmin.objects.get(username="ali")
    row = c.get("/api/v1/admin/agency/admins/ali/").json()
    b = row["bytes"]
    assert b["limit"] == a.admin_limit_bytes and _fmt_bytes(b["limit"]) == row["admin_limit_fmt"]
    assert _fmt_bytes(b["total_sold"]) == row["total_sold_fmt"] and _fmt_bytes(b["used"]) == row["used_fmt"]
    assert _fmt_bytes(b["remaining"]) == row["remaining_fmt"] and _fmt_bytes(b["hidden"]) == _enrich(a)["hidden_traffic_fmt"]
    assert b["sold_limit"] == _enrich(a)["sold_limit_value"] and _fmt_bytes(b["deleted"]) == row["deleted_used_fmt"]
    d = c.get("/api/v1/admin/agency/").json()
    assert _fmt_bytes(d["bytes"]["total_sold"]) == d["total_sold_fmt"] and _fmt_bytes(d["bytes"]["hidden"]) == d["total_hidden_fmt"]
    p = c.post(URL + "preview/", {"action": "set", "value_gb": 2048}, format="json").json()
    assert p["new_limit_bytes"] == 2 * 1024 * GB and p["remaining_after_bytes"] == 2 * 1024 * GB - 400 * GB
