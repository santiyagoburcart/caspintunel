"""Multi-tenant Phase 1 Release C (v1.42.0, docs/multi-tenant.md §3, §18):

- strict mode: in the web process a tenant-table query with no tenant raises NoTenant (lenient = warning + default);
  requests get their tenant from the middleware; background processes use the default tenant;
- `tenant` is NOT NULL on the tenant tables — a row can't be saved without a store;
- the old global unique rules are gone: two stores can have the same username / page slug / discount code / tag, each
  store signs in its own customer, and inside one store a duplicate is still a clean 400 (never a 500).
"""
import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.crm.models import DiscountCode, Tag
from apps.plans.models import Plan
from apps.settings_app.models import Page
from apps.tenancy import context
from apps.tenancy.models import Tenant, TenantDomain

pytestmark = pytest.mark.django_db
B_HOST = "store-c.test"


@pytest.fixture
def store_b(_default_tenant):
    b = Tenant.objects.create(slug="store-c", name="Store C", status="active", reseller_username="reseller-c")
    TenantDomain.objects.create(tenant=b, host=B_HOST, state="active")
    return b


@pytest.fixture
def no_tenant():
    """Leave the test's default tenant: like code running outside any request."""
    token = context.set_tenant(None)
    yield
    context.reset_tenant(token)


@pytest.fixture
def web_process(monkeypatch):
    monkeypatch.setattr(context, "IN_WEB_PROCESS", True)


# --- strict mode --------------------------------------------------------------------------------------------------
def test_strict_web_process_without_a_tenant_fails_closed(settings, web_process, no_tenant):
    settings.TENANCY_STRICT = True
    with pytest.raises(context.NoTenant):
        list(Plan.objects.all())
    with context.tenant_context(context.default_tenant_id()):
        assert Plan.objects.count() >= 0                                            # with a tenant it works


def test_strict_requests_get_their_tenant_from_the_middleware(settings, web_process, store_b):
    settings.TENANCY_STRICT = True
    with context.tenant_context(store_b.pk):
        Plan.objects.create(name_fa="c", name_en="StoreCPlan", price=1, duration_days=1, is_active=True)
    token = context.set_tenant(None)
    try:
        ours = APIClient().get("/api/v1/plans/")
        theirs = APIClient(HTTP_HOST=B_HOST).get("/api/v1/plans/")
    finally:
        context.reset_tenant(token)
    assert ours.status_code == 200 and b"StoreCPlan" not in ours.content
    assert theirs.status_code == 200 and b"StoreCPlan" in theirs.content


@pytest.fixture
def warnings_seen(monkeypatch):
    seen = []                                         # the "caspintunel" logger does not propagate to caplog
    monkeypatch.setattr(context.log, "warning", lambda msg, *a, **k: seen.append(msg % a if a else msg))
    return seen


def test_lenient_switch_falls_back_with_a_warning(settings, web_process, no_tenant, warnings_seen):
    settings.TENANCY_STRICT = False
    list(Plan.objects.all())
    assert any("query without a tenant" in m for m in warnings_seen)


def test_background_processes_use_the_default_tenant(settings, no_tenant, warnings_seen):
    settings.TENANCY_STRICT = True                                                   # not a web process (no wsgi)
    assert context.current_tenant_id() == context.default_tenant_id()
    list(Plan.objects.all())
    assert warnings_seen == []


# --- NOT NULL -----------------------------------------------------------------------------------------------------
def test_a_tenant_row_cannot_be_saved_without_a_store():
    with context.unscoped():                                                         # unscoped: nothing fills tenant
        with pytest.raises(IntegrityError), transaction.atomic():
            Plan.objects.create(name_fa="x", name_en="x", price=1, duration_days=1)
    p = Plan.objects.create(name_fa="y", name_en="y", price=1, duration_days=1)
    with context.unscoped(), pytest.raises(IntegrityError), transaction.atomic():
        Plan.objects.filter(pk=p.pk).update(tenant=None)


# --- per-store unique rules ---------------------------------------------------------------------------------------
def test_same_names_in_two_stores_and_each_store_signs_in_its_own_customer(store_b):
    ours = User.objects.create_user("samename", "Ours-Pass1!")
    Page.objects.create(slug="same-page", title_fa="a", title_en="ours")
    DiscountCode.objects.create(code="SAMEOFF")
    Tag.objects.create(name="sametag")
    with context.tenant_context(store_b.pk):
        theirs = User.objects.create_user("samename", "Their-Pass1!")
        Page.objects.create(slug="same-page", title_fa="b", title_en="theirs")
        DiscountCode.objects.create(code="SAMEOFF")
        Tag.objects.create(name="sametag")
    assert ours.pk != theirs.pk and ours.referral_code and theirs.referral_code

    def login(host, pwd):
        return APIClient(HTTP_HOST=host).post("/api/v1/auth/login/", {"username": "samename", "password": pwd}, format="json")

    r = login("testserver", "Ours-Pass1!")
    assert r.status_code == 200, r.content
    me = APIClient(); me.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    assert me.get("/api/v1/auth/me/").json()["id"] == ours.pk
    assert login("testserver", "Their-Pass1!").status_code == 401                    # B's password is not ours
    r = login(B_HOST, "Their-Pass1!")
    assert r.status_code == 200, r.content
    on_b = APIClient(HTTP_HOST=B_HOST); on_b.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    assert on_b.get("/api/v1/auth/me/").json()["id"] == theirs.pk
    assert APIClient().get("/api/v1/pages/same-page/").json()["title_en"] == "ours"
    assert APIClient(HTTP_HOST=B_HOST).get("/api/v1/pages/same-page/").json()["title_en"] == "theirs"


def test_inside_one_store_duplicates_are_still_refused(store_b):
    from apps.payments_sms.tests.test_blu import staff_client

    User.objects.create_user("dupuser", "Str0ngPass!")
    with pytest.raises(IntegrityError), transaction.atomic():                       # the per-store constraint
        User.objects.create_user("dupuser", "Str0ngPass!")
    admin = staff_client("super", "release-c-boss")
    r = admin.post("/api/v1/admin/users/", {"username": "dupuser", "password": "Str0ngPass!1"}, format="json")
    assert r.status_code == 400 and "username" in r.json(), r.content
    with context.tenant_context(store_b.pk):
        User.objects.create_user("onlyinb", "Str0ngPass!")
    r = admin.post("/api/v1/admin/users/", {"username": "onlyinb", "password": "Str0ngPass!1"}, format="json")
    assert r.status_code == 201, r.content                                           # B's name is free in our store
    Page.objects.create(slug="dup-page", title_fa="a", title_en="a")
    r = admin.post("/api/v1/admin/pages/", {"slug": "dup-page", "title_fa": "b", "title_en": "b", "body_fa": "b"}, format="json")
    assert r.status_code == 400 and "slug" in r.json(), r.content
    other = User.objects.create_user("tgowner2", "Str0ngPass!")
    User.objects.filter(pk=User.objects.get(username="dupuser").pk).update(telegram_id=777000111)
    r = admin.patch(f"/api/v1/admin/users/{other.pk}/", {"telegram_id": 777000111}, format="json")
    assert r.status_code == 400 and "telegram_id" in r.json(), r.content
