"""Multi-tenant Phase 1 Release A (docs/multi-tenant.md §3, §18): every model is classified (tenant / nullable /
platform) and tenant models carry the `tenant` column; the default tenant + its domain exist; the backfill fills only
rows without a tenant (platform rows stay NULL) and is idempotent; only one default tenant can exist."""
import pytest
from django.apps import apps

from apps.accounts.models import Staff, User
from apps.notifications.models import PushSubscription
from apps.plans.models import Plan
from apps.settings_app.models import Page
from apps.tenancy import registry
from apps.tenancy.backfill import backfill, ensure_default
from apps.tenancy.models import Tenant, TenantDomain

pytestmark = pytest.mark.django_db


def _project_models():
    return {f"{m._meta.app_label}.{m.__name__}" for m in apps.get_models()
            if m._meta.app_label in registry.PROJECT_APPS and not m._meta.auto_created}


def test_every_model_is_classified_exactly_once():
    lists = registry.TENANT + registry.NULLABLE + registry.PLATFORM
    assert len(lists) == len(set(lists)), "a model is listed twice"
    missing = _project_models() - set(lists)
    assert not missing, f"classify these in apps/tenancy/registry.py: {sorted(missing)}"
    assert not set(lists) - _project_models(), "registry names a model that does not exist"


def test_tenant_column_matches_the_classification():
    for label in registry.TENANT + registry.NULLABLE:
        f = apps.get_model(label)._meta.get_field("tenant")
        assert f.related_model is Tenant, label
        assert f.null is (label in registry.NULLABLE), f"{label}: tenant must be NOT NULL unless NULLABLE (Release C)"
    for label in registry.PLATFORM:
        names = {f.name for f in apps.get_model(label)._meta.get_fields()}
        # platform tables keyed BY a store (its domains, its bot) — set by our staff, never scoped
        assert "tenant" not in names or label in ("tenancy.TenantDomain", "tenancy.TenantBot"), label


def test_default_tenant_and_backfill():
    t = ensure_default(domain="Caspintunel.com.")
    assert t.is_default and t.status == "active" and ensure_default().pk == t.pk           # idempotent, one default
    assert TenantDomain.objects.filter(tenant=t, host="caspintunel.com", state="active").exists()
    with pytest.raises(Exception):                                                       # PROTECT: a tenant with data stays
        t.delete()
    u = User.objects.create_user("c1", "Str0ngPass!")
    plan = Plan.objects.create(name_fa="پلن", name_en="Plan", price=1000, duration_days=30)
    page = Page.objects.create(slug="mt-test-page", title_fa="صفحه", title_en="Page")
    staff = Staff.objects.create(username="op", password_hash="x")
    push_c = PushSubscription.objects.create(endpoint="https://p/1", endpoint_hash="h1", p256dh="k", auth="a", user=u)
    push_s = PushSubscription.objects.create(endpoint="https://p/2", endpoint_hash="h2", p256dh="k", auth="a", staff=staff)
    assert u.tenant_id == t.pk and plan.tenant_id == t.pk                               # Release B: filled on create
    # a customer's browser saved without a tenant (NULLABLE model) — tenant tables can't hold NULL any more (Release C)
    from apps.tenancy.context import unscoped

    with unscoped():
        PushSubscription.objects.filter(pk=push_c.pk).update(tenant=None)
    done = backfill()
    assert done["notifications.PushSubscription"] == 1 and done["accounts.User"] == 0
    for obj in (u, plan, page, push_c):
        obj.refresh_from_db()
        assert obj.tenant_id == t.pk, obj
    staff.refresh_from_db(); push_s.refresh_from_db()
    assert staff.tenant_id is None and push_s.tenant_id is None                         # platform rows stay NULL
    assert sum(backfill().values()) == 0                                                  # nothing left to fill
    assert seeded_ok()
    # a row of another tenant is never moved to the default
    other = Tenant.objects.create(slug="store-a", name="Store A")
    u2 = User.objects.create_user("c2", "Str0ngPass!")
    User.objects.filter(pk=u2.pk).update(tenant=other)
    backfill()
    with unscoped():
        assert User.objects.get(pk=u2.pk).tenant_id == other.pk


def seeded_ok() -> bool:
    """Rows seeded by earlier migrations (ticket topics, CRM reasons, retention rules) belong to the default store."""
    from apps.crm.models import CaseReason
    from apps.tickets.models import TicketTopic

    return not TicketTopic.objects.filter(tenant__isnull=True).exists() and not CaseReason.objects.filter(tenant__isnull=True).exists()


def test_only_one_default_tenant():
    ensure_default()
    assert Tenant.objects.filter(is_default=True).count() == 1
    with pytest.raises(ValueError):
        Tenant.objects.create(slug="b", name="B", is_default=True)
