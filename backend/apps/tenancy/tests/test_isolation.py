"""Multi-tenant isolation (docs/multi-tenant.md §3, Phase 1 Release B) — the release gate.

Store B gets one row per tenant table it matters for, each carrying a marker text. Then, on OUR host (the default
tenant), every admin and customer list endpoint is called and must never show a B marker; B's ids on detail URLs must be
404; B's customer token is refused on our host; unknown hosts are 404; and querysets built under one tenant run for the
tenant current when the SQL is compiled (DRF builds `queryset = Model.objects.all()` once at import).
"""
import re
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.crm.models import DiscountCode, Tag
from apps.notifications.models import Notification, NotificationType
from apps.orders.models import Order, OrderStatus, OrderType
from apps.payments_sms.models import BankCard, Payment, PaymentStatus
from apps.plans.models import Plan
from apps.settings_app.models import Page
from apps.tenancy import context
from apps.tenancy.models import Tenant, TenantDomain
from apps.tickets.models import Ticket, TicketTopic

pytestmark = pytest.mark.django_db
B_HOST = "store-b.test"
MARK = "ZZBMARK"


@pytest.fixture
def store_b(_default_tenant):
    b = Tenant.objects.create(slug="store-b", name="Store B", status="active", reseller_username="reseller-b")
    TenantDomain.objects.create(tenant=b, host=B_HOST, state="active")
    with context.tenant_context(b.pk):
        u = User.objects.create_user(f"{MARK.lower()}user", "Str0ngPass!", name=f"{MARK} customer")
        plan = Plan.objects.create(name_fa=f"{MARK} plan", name_en=f"{MARK} plan", price=111000, duration_days=30)
        o = Order.objects.create(user=u, plan=plan, type=OrderType.NEW, status=OrderStatus.COMPLETED, amount=Decimal(111000),
                                 amount_unique=Decimal(111111), unique_expire_at=timezone.now() + timedelta(minutes=30),
                                 requested_account_name=f"{MARK.lower()}acc")
        p = Payment.objects.create(order=o, amount=Decimal(111111), status=PaymentStatus.APPROVED, method="card_manual",
                                   receipt_ref=f"{MARK}REF", confirmed_at=timezone.now())
        topic = TicketTopic.objects.create(name_fa=f"{MARK} topic", name_en=f"{MARK} topic")
        t = Ticket.objects.create(user=u, topic=topic, subject=f"{MARK} ticket")
        DiscountCode.objects.create(code=f"{MARK}OFF")
        Tag.objects.create(name=f"{MARK}tag")
        Page.objects.create(slug=f"{MARK.lower()}-page", title_fa=f"{MARK} page", title_en=f"{MARK} page")
        Notification.objects.create(type=NotificationType.values[0], title=f"{MARK} note", body=f"{MARK} body", target_user=u)
        BankCard.objects.create(card_number="6037990000000001", holder_name=f"{MARK} holder")
    return {"tenant": b, "user": u, "plan": plan, "order": o, "payment": p, "ticket": t}


def _admin():
    from apps.payments_sms.tests.test_blu import staff_client

    return staff_client("super", "iso-boss")


def _list_urls(prefix: str) -> list[str]:
    """Every GET-able URL under prefix that needs no path argument (built from the live resolver)."""
    out = []

    def walk(patterns, pre=""):
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns, pre + str(p.pattern))
            elif isinstance(p, URLPattern):
                full = (pre + str(p.pattern)).replace("^", "").replace("$", "")
                if "<" in full or "(?P" in full or "\\" in full or "format" in full:
                    continue
                out.append("/" + full)
    walk(get_resolver().url_patterns)
    return sorted({u for u in out if u.startswith(prefix)})


# platform pages (no tenant data) or ones that call outside services — not part of the sweep
SKIP = re.compile(r"/(agency|domain|paths|system|backups|monitoring|health|resources|docs|email|integrations|telegram-stats|"
                  r"bots|apps|permissions|roles|staff|settings|branding|themes|panels|sms-sources|push|auth)/")


def test_staff_lists_on_our_host_never_show_store_b(store_b):
    admin = _admin()
    urls = [u for u in _list_urls("/api/v1/admin/") if not SKIP.search(u)]
    assert len(urls) > 30, urls                                                     # the sweep really covers the panel
    leaks, errors = [], []
    for url in urls:
        r = admin.get(url)
        if r.status_code >= 500:
            errors.append((url, r.status_code))
        if MARK.encode() in r.content or MARK.lower().encode() in r.content:
            leaks.append(url)
    assert not leaks, f"store B data visible on our host: {leaks}"
    assert not errors, errors


def test_the_sweep_does_catch_a_leak(store_b):
    """Canary: with scoping switched off the same sweep MUST see store B — proof the sweep can fail."""
    admin = _admin()
    urls = [u for u in _list_urls("/api/v1/admin/") if not SKIP.search(u)]
    with context.unscoped():
        seen = [u for u in urls if MARK.encode() in admin.get(u).content]
    assert len(seen) >= 5, seen


@pytest.mark.parametrize("url", ["/api/v1/admin/users/{user}/", "/api/v1/admin/transactions/{payment}/",
                                 "/api/v1/admin/users/{user}/orders/", "/api/v1/admin/tickets/{ticket}/"])
def test_store_b_ids_are_404_on_our_host(store_b, url):
    r = _admin().get(url.format(user=store_b["user"].pk, payment=store_b["payment"].pk, ticket=store_b["ticket"].pk))
    assert r.status_code == 404 or MARK.encode() not in r.content, (url, r.status_code)


def test_customer_token_of_store_b_is_refused_on_our_host(store_b):
    c = APIClient(HTTP_HOST=B_HOST)
    r = c.post("/api/v1/auth/login/", {"username": f"{MARK.lower()}user", "password": "Str0ngPass!"}, format="json")
    assert r.status_code == 200, r.content
    access = r.json()["access"]
    on_b = APIClient(HTTP_HOST=B_HOST); on_b.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    assert on_b.get("/api/v1/orders/").status_code == 200
    ours = APIClient(); ours.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    r = ours.get("/api/v1/orders/")
    assert r.status_code == 401 and r.json().get("code") in ("wrong_store", "user_not_found"), r.content
    # and the same username / password does not sign in on our host
    assert APIClient().post("/api/v1/auth/login/", {"username": f"{MARK.lower()}user", "password": "Str0ngPass!"},
                            format="json").status_code == 401


def test_customer_lists_of_our_store_never_show_store_b(store_b):
    u = User.objects.create_user("ours1", "Str0ngPass!")
    c = APIClient(); c.force_authenticate(u)
    for url in ("/api/v1/orders/", "/api/v1/services/", "/api/v1/notifications/", "/api/v1/plans/", "/api/v1/pages/",
                "/api/v1/tickets/", "/api/v1/tickets/topics/", "/api/v1/orders/manual-invoices/", "/api/v1/payments/cards/"):
        r = c.get(url)
        assert r.status_code < 500 and MARK.encode() not in r.content, url


def test_unknown_host_is_404_and_creates_go_to_the_current_tenant(store_b):
    assert APIClient(HTTP_HOST="stranger.example").get("/api/v1/plans/").status_code == 404
    with context.tenant_context(store_b["tenant"].pk):
        p = Plan.objects.create(name_fa="x", name_en="x", price=1, duration_days=1)
    assert p.tenant_id == store_b["tenant"].pk
    assert not Plan.objects.filter(pk=p.pk).exists()                                 # we are in the default tenant here


def test_queryset_built_once_runs_for_the_current_tenant(store_b):
    qs = Plan.objects.all()                                  # built in the default tenant, like a DRF class attribute
    with context.tenant_context(store_b["tenant"].pk):
        names = [p.name_en for p in qs.all()]
    assert any(MARK in n for n in names)
    assert not any(MARK in p.name_en for p in qs.all())


def test_unscoped_is_used_only_where_allowed():
    root = Path(__file__).resolve().parents[3]                                       # backend/
    users = set()
    for f in root.joinpath("apps").rglob("*.py"):
        rel = str(f.relative_to(root))
        if "/tests/" in rel or "/migrations/" in rel:
            continue
        if re.search(r"\bunscoped\(\)", f.read_text(encoding="utf-8")):
            users.add(rel)
    assert users <= context.ALLOWED_UNSCOPED, f"unscoped() outside the allow-list: {sorted(users - context.ALLOWED_UNSCOPED)}"
