"""Multi-tenant Phase 2 Release A (v1.43): our staff open a store («فروشگاه» on the agency admin page); a store has its own
branding, settings (TENANT_KEYS), pages and theme; on a store's domain the admin API runs in store mode (only views that
opt in answer — never agency, Blu, ops…) and platform endpoints are 404; draft / suspended stores are not reachable."""
import pytest
from rest_framework.test import APIClient

from apps.agency.models import PanelAdmin
from apps.common.models import AuditLog
from apps.payments_sms.tests.test_blu import staff_client
from apps.settings_app.models import Page, Setting, SiteConfig, TenantBranding, TenantSetting, Theme
from apps.tenancy import context
from apps.tenancy.models import Tenant, TenantDomain

pytestmark = pytest.mark.django_db
HOST = "shop.reseller.test"


@pytest.fixture
def admin_row():
    return PanelAdmin.objects.create(username="reseller1")


def _on(client, host):
    client.defaults["HTTP_HOST"] = host
    return client


@pytest.fixture
def store(admin_row, _default_tenant):
    Page.objects.update_or_create(slug="rules", defaults={"title_fa": "قوانین ما", "title_en": "Our rules",
                                                          "body_fa": "متن", "body_en": "text", "is_active": True})
    boss = staff_client("super", "store-boss")
    r = boss.post("/api/v1/admin/agency/panel-admins/reseller1/store/", {"name": "فروشگاه یک"}, format="json")
    assert r.status_code == 201, r.content
    t = Tenant.objects.get(reseller_username="reseller1")
    TenantDomain.objects.create(tenant=t, host=HOST, state="active")
    return t


def test_our_staff_open_a_store_as_a_draft_with_its_own_branding_and_pages(store):
    assert store.status == "draft" and not store.is_default and store.slug == "reseller1"
    with context.tenant_context(store.pk):
        assert TenantBranding.objects.get().site_name_fa == "فروشگاه یک"
        assert Page.objects.get(slug="rules").title_fa == "قوانین ما"            # a copy of ours to start from
    assert AuditLog.objects.filter(action="store.enabled", detail__reseller="reseller1").exists()
    boss = staff_client("super", "store-boss2")
    assert boss.post("/api/v1/admin/agency/panel-admins/reseller1/store/", {}, format="json").status_code == 409
    assert staff_client(["agency.view"], "viewer").post("/api/v1/admin/agency/panel-admins/reseller1/store/", {},
                                                         format="json").status_code == 403
    body = staff_client(["agency.view"], "viewer2").get("/api/v1/admin/agency/panel-admins/reseller1/store/").json()
    assert body["store"]["status"] == "draft" and body["store"]["domains"][0]["host"] == HOST
    assert body["store"]["reachable"] is False


def test_only_an_active_store_is_reachable(store):
    assert APIClient(HTTP_HOST=HOST).get("/api/v1/config/").status_code == 404          # draft
    boss = staff_client("super", "act-boss")
    r = boss.patch("/api/v1/admin/agency/panel-admins/reseller1/store/", {"status": "active"}, format="json")
    assert r.status_code == 200 and r.json()["store"]["reachable"] is True
    cfg = APIClient(HTTP_HOST=HOST).get("/api/v1/config/").json()
    assert cfg["site_name_fa"] == "فروشگاه یک"
    assert APIClient().get("/api/v1/config/").json()["site_name_fa"] == SiteConfig.load().site_name_fa   # ours unchanged
    boss.patch("/api/v1/admin/agency/panel-admins/reseller1/store/", {"status": "suspended"}, format="json")
    assert APIClient(HTTP_HOST=HOST).get("/api/v1/config/").status_code == 404
    assert AuditLog.objects.filter(action="store.updated", target_id=store.pk).count() == 2


@pytest.fixture
def live(store):
    Tenant.objects.filter(pk=store.pk).update(status="active")
    from django.core.cache import cache

    cache.clear()
    return store


def test_store_mode_admin_api_answers_only_store_views(live):
    boss = _on(staff_client("super", "mode-boss"), HOST)
    me = boss.get("/api/v1/admin/auth/me/").json()
    assert me["store"]["id"] == live.pk and me["store"]["name"] == "فروشگاه یک"
    for url in ("/api/v1/admin/agency/", "/api/v1/admin/payments/blu-transactions/", "/api/v1/admin/monitoring/",
                "/api/v1/admin/backups/", "/api/v1/admin/transactions/", "/api/v1/admin/roles/"):
        assert boss.get(url).status_code == 403, url                      # Super Admin too: platform pages
    for url in ("/api/v1/admin/users/", "/api/v1/admin/pages/", "/api/v1/admin/themes/", "/api/v1/admin/branding/",
                "/api/v1/admin/settings/", "/api/v1/admin/dashboard/"):
        assert boss.get(url).status_code == 200, url
    dash = boss.get("/api/v1/admin/dashboard/").json()
    assert dash["store"] is True and dash["health"] is None and dash["resources"] is None
    assert staff_client("super", "ours").get("/api/v1/admin/auth/me/").json()["store"] is None


def test_platform_endpoints_are_404_on_a_store_domain(live):
    c = APIClient(HTTP_HOST=HOST)
    for url in ("/api/v1/agency/auth/me/", "/api/v1/payments/blu/webhook/", "/api/v1/payments/sms/ping/",
                "/admin/", "/api/schema/", "/api/v1/payments/1/approve/"):
        assert c.get(url).status_code == 404, url
    assert APIClient().get("/api/v1/payments/sms/ping/").status_code != 404           # ours still answers


def test_store_settings_are_only_tenant_keys_and_never_touch_ours(live):
    boss = _on(staff_client("super", "set-boss"), HOST)
    keys = {s["key"] for s in boss.get("/api/v1/admin/settings/").json()["settings"]}
    assert "referral_required" in keys and "backup_interval_minutes" not in keys and "rounded_auto_enabled" not in keys
    assert boss.put("/api/v1/admin/settings/", {"backup_interval_minutes": 5}, format="json").status_code == 403
    r = boss.put("/api/v1/admin/settings/", {"referral_required": True}, format="json")
    assert r.status_code == 200, r.content
    assert not Setting.objects.filter(key="referral_required").exists()               # ours untouched
    from apps.settings_app.utils import get_setting

    with context.tenant_context(live.pk):
        assert TenantSetting.objects.get(key="referral_required").value == "true"
        assert get_setting("referral_required", False) is True
    assert get_setting("referral_required", False) is False                            # default tenant


def test_store_branding_edits_the_store_not_ours(live):
    ours = SiteConfig.load().site_name_fa
    boss = _on(staff_client("super", "brand-boss"), HOST)
    r = boss.patch("/api/v1/admin/branding/", {"site_name_fa": "شاپ نو", "support_telegram": "shopnew"}, format="json")
    assert r.status_code == 200, r.content
    assert SiteConfig.load().site_name_fa == ours
    assert APIClient(HTTP_HOST=HOST).get("/api/v1/config/").json()["site_name_fa"] == "شاپ نو"


def test_store_themes_are_its_own_plus_built_in(live):
    builtin = Theme.objects.create(name="Built-in", palette={"style": "caspian"}, is_active=True)
    boss = _on(staff_client("super", "theme-boss"), HOST)
    r = boss.post("/api/v1/admin/themes/", {"name": "Shop Green", "palette": {"style": "caspian", "primary": "#0a0"}},
                  format="json")
    assert r.status_code == 201, r.content
    mine = Theme.objects.get(name="Shop Green")
    assert mine.tenant_id == live.pk and not mine.is_active
    assert boss.patch(f"/api/v1/admin/themes/{builtin.id}/", {"name": "x"}, format="json").status_code == 403
    assert boss.post(f"/api/v1/admin/themes/{mine.id}/activate/").status_code == 200
    builtin.refresh_from_db()
    assert builtin.is_active                                                           # ours still active for us
    assert APIClient(HTTP_HOST=HOST).get("/api/v1/theme/").json()["name"] == "Shop Green"
    assert APIClient().get("/api/v1/theme/").json()["name"] == "Built-in"
    names = [t["name"] for t in staff_client("super", "our-theme").get("/api/v1/admin/themes/").json()["results"]]
    assert "Shop Green" not in names                                                    # never another store's theme


def test_store_pages_are_separate(live):
    with context.tenant_context(live.pk):
        Page.objects.filter(slug="rules").update(title_fa="قوانین فروشگاه")
    assert APIClient(HTTP_HOST=HOST).get("/api/v1/pages/rules/").json()["title_fa"] == "قوانین فروشگاه"
    assert APIClient().get("/api/v1/pages/rules/").json()["title_fa"] == "قوانین ما"
