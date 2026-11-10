"""Multi-tenant Phase 7 Release B (v1.51): the store's own tickets + discounts in its panel, store settings, store caps.

* Reverse isolation sweep (release gate for store pages): on a store's domain no admin endpoint shows OUR data or OUR staff.
* A store can never change one of our global settings; ticket rules it sets are its own (TENANT_KEYS).
* Ticket assignment / scopes reach only the store's staff.
* Throttle buckets are per store; a per-store cap (`limits.requests_per_minute`) answers 429 for that store only + alerts us.
* Mail for a store carries its support email as Reply-To.
"""
import pytest
from django.core.mail import EmailMessage
from rest_framework.test import APIClient

from apps.accounts.models import Staff, User
from apps.crm.models import DiscountCode
from apps.plans.models import Plan
from apps.settings_app.models import Setting, TenantSetting
from apps.tenancy import context
from apps.tenancy.models import Tenant, TenantDomain
from apps.tenancy.tests.test_isolation import _list_urls
from apps.tickets.models import Ticket, TicketTopic

pytestmark = pytest.mark.django_db
HOST = "shop-p7b.example"
OURS = "ZZOURMARK"


@pytest.fixture
def store(_default_tenant):
    t = Tenant.objects.create(slug="s7b", name="Store 7B", status="active", reseller_username="p7badmin")
    TenantDomain.objects.create(tenant=t, host=HOST, state="active")
    return t


@pytest.fixture
def our_data(_default_tenant):
    u = User.objects.create_user(f"{OURS.lower()}user", "Str0ngPass!", name=f"{OURS} customer")
    topic = TicketTopic.objects.create(name_fa=f"{OURS} topic", name_en=f"{OURS} topic")
    Ticket.objects.create(user=u, topic=topic, subject=f"{OURS} ticket")
    DiscountCode.objects.create(code=f"{OURS}OFF")
    Plan.objects.create(name_fa=f"{OURS} plan", name_en=f"{OURS} plan", price=1000, duration_days=30)
    Staff.objects.create(username=f"{OURS.lower()}staff", is_superadmin=True, telegram_id=5151)
    return {"topic": topic}


def _store_admin():
    from apps.payments_sms.tests.test_blu import staff_client

    c = staff_client("super", "p7b-boss")
    c.defaults["HTTP_HOST"] = HOST
    return c


def test_store_panel_never_shows_our_data_or_our_staff(store, our_data):
    c = _store_admin()
    urls = _list_urls("/api/v1/admin/")
    assert len(urls) > 30
    opened, leaks, errors = [], [], []
    for url in urls:
        r = c.get(url)
        if r.status_code >= 500:
            errors.append((url, r.status_code))
        if r.status_code == 200:
            opened.append(url)
            if OURS.encode() in r.content or OURS.lower().encode() in r.content:
                leaks.append(url)
    assert not leaks, f"our data visible on a store's panel: {leaks}"
    assert not errors, errors
    for page in ("/api/v1/admin/tickets/", "/api/v1/admin/tickets/topics/", "/api/v1/admin/discounts/",
                 "/api/v1/admin/tickets/staff/", "/api/v1/admin/tickets/settings/"):
        assert page in opened, (page, opened)                                  # the new store pages really answer


def test_store_ticket_rules_are_its_own_and_ours_stay_ours(store):
    from apps.settings_app.utils import StoreSettingRefused, set_setting
    from apps.tickets import rules

    c = _store_admin()
    r = c.patch("/api/v1/admin/tickets/settings/", {"tickets_auto_close_days": 21, "tickets_show_staff_name": True},
                format="json")
    assert r.status_code == 200, r.content
    assert not Setting.objects.filter(key="tickets_auto_close_days").exists()  # our setting untouched
    assert rules.setting("tickets_auto_close_days") == 7
    with context.tenant_context(store.pk):
        assert rules.setting("tickets_auto_close_days") == 21 and rules.bool_setting("tickets_show_staff_name") is True
        assert TenantSetting.objects.filter(key="tickets_auto_close_days").exists()
        with pytest.raises(StoreSettingRefused):
            set_setting("agency_sync_enabled", True, "bool")                   # never one of our global settings


def test_store_tickets_assign_only_to_store_staff(store, our_data):
    ours = Staff.objects.get(username=f"{OURS.lower()}staff")
    theirs = Staff.objects.create(username="their-7b", is_superadmin=True, tenant=store)
    with context.tenant_context(store.pk):
        u = User.objects.create_user("p7bcust", "Str0ngPass!")
        topic = TicketTopic.objects.create(name_fa="t", name_en="t")
        t = Ticket.objects.create(user=u, topic=topic, subject="help")
    c = _store_admin()
    assert c.post(f"/api/v1/admin/tickets/{t.pk}/assign/", {"staff": ours.pk}, format="json").status_code == 404
    assert c.put(f"/api/v1/admin/tickets/staff-scopes/{ours.pk}/", {"topic_ids": []}, format="json").status_code in (404, 405)
    r = c.post(f"/api/v1/admin/tickets/{t.pk}/assign/", {"staff": theirs.pk}, format="json")
    assert r.status_code == 200, r.content
    assert [s["username"] for s in c.get("/api/v1/admin/tickets/staff/").json()] == ["their-7b"]


# ------------------------------------------------------------------ throttles
def test_throttle_buckets_are_per_store(store):
    from rest_framework.test import APIRequestFactory

    from apps.common.throttling import AnonRateThrottle

    req = APIRequestFactory().get("/", REMOTE_ADDR="10.0.0.9")
    req.META["HTTP_X_FORWARDED_FOR"] = "10.0.0.9"
    ours = AnonRateThrottle().get_ident(req)
    with context.tenant_context(store.pk):
        theirs = AnonRateThrottle().get_ident(req)
    assert theirs == f"t{store.pk}:{ours}" and not ours.startswith("t")


def test_store_cap_answers_429_for_that_store_only_and_alerts_us(store, monkeypatch, boss=None):
    from django.core.cache import cache

    from apps.common.throttling import StoreTotalThrottle
    from apps.tenancy import stores

    alerts = []
    monkeypatch.setattr("apps.common.staff_alert.alert_staff", lambda text, **kw: alerts.append(kw) or 1)
    with pytest.raises(stores.StoreError):
        stores.update(store, {"requests_per_minute": 5})                     # below 60 = a typo, refused
    stores.update(store, {"requests_per_minute": 60})
    cache.clear()
    with context.tenant_context(store.pk):
        results = [StoreTotalThrottle().allow_request(None, None) for _ in range(61)]
    assert results[:60] == [True] * 60 and results[60] is False
    assert alerts and alerts[0]["platform"] is True
    assert all(StoreTotalThrottle().allow_request(None, None) for _ in range(100))   # ours: never capped
    stores.update(store, {"requests_per_minute": 0})
    store.refresh_from_db()
    assert store.limits["requests_per_minute"] is None


# ------------------------------------------------------------------ mail
def test_store_mail_replies_go_to_its_support_email(store):
    from apps.common.mail import _store_sender
    from apps.settings_app.models import TenantBranding

    with context.tenant_context(store.pk):
        TenantBranding.objects.create(site_name_fa="هفت ب", support_email="help@shop-p7b.example")
        m = [EmailMessage("s", "b", "noreply@caspin.example", ["a@b.c"])]
        _store_sender(m)
    assert m[0].reply_to == ["help@shop-p7b.example"] and m[0].from_email.endswith("<noreply@caspin.example>")
    c = _store_admin()
    r = c.get("/api/v1/admin/branding/")
    assert r.status_code == 200 and r.json().get("support_email") == "help@shop-p7b.example"
